# Deploy (or redeploy) Ticket Triage Copilot to AWS ECS Fargate.
# Run from the project root:   powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1
# Safe to re-run: existing resources are reused; a new image is pushed and the service is updated.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\common.ps1"

$TAG = "v" + (Get-Date -Format "yyyyMMdd-HHmm")

Step "1/9 Checking AWS identity"
$ACCOUNT = AwsOk sts get-caller-identity --query Account --output text
Write-Host "Account $ACCOUNT, region $REGION"

Step "2/9 Secrets Manager: storing GROQ_API_KEY + SERVICE_API_KEY from .env"
$json = @{ GROQ_API_KEY = (EnvVal "GROQ_API_KEY"); SERVICE_API_KEY = (EnvVal "SERVICE_API_KEY") } | ConvertTo-Json -Compress
$tmp = Join-Path $env:TEMP "triage-secret.json"
Set-Content -Path $tmp -Value $json -Encoding ascii -NoNewline
$SECRET_ARN = AwsTry secretsmanager describe-secret --secret-id $SECRET_NAME --region $REGION --query ARN --output text
if (-not $SECRET_ARN) {
    $SECRET_ARN = AwsOk secretsmanager create-secret --name $SECRET_NAME --secret-string "file://$tmp" --region $REGION --query ARN --output text
} else {
    AwsOk secretsmanager put-secret-value --secret-id $SECRET_NAME --secret-string "file://$tmp" --region $REGION | Out-Null
}
Remove-Item $tmp
Write-Host "Secret: $SECRET_ARN"

Step "3/9 ECR: build, log in, push image ($TAG)"
$REGISTRY = "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
$IMAGE = "$REGISTRY/${APP}:$TAG"
if (-not (AwsTry ecr describe-repositories --repository-names $APP --region $REGION)) {
    AwsOk ecr create-repository --repository-name $APP --region $REGION | Out-Null
}
docker compose build
if ($LASTEXITCODE -ne 0) { Fail "docker build failed (is Docker Desktop running?)" }
$pw = AwsOk ecr get-login-password --region $REGION
$pw | docker login --username AWS --password-stdin $REGISTRY
if ($LASTEXITCODE -ne 0) { Fail "docker login to ECR failed" }
docker tag "${APP}:latest" $IMAGE
docker push $IMAGE
if ($LASTEXITCODE -ne 0) { Fail "docker push failed" }

Step "4/9 IAM: task execution role (pull image, write logs, read the one secret)"
$trust = Join-Path $env:TEMP "triage-trust.json"
Set-Content -Path $trust -Encoding ascii -Value '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if (-not (AwsTry iam get-role --role-name $ROLE)) {
    AwsOk iam create-role --role-name $ROLE --assume-role-policy-document "file://$trust" | Out-Null
    AwsOk iam attach-role-policy --role-name $ROLE --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" | Out-Null
    Write-Host "waiting 10s for IAM to propagate..."; Start-Sleep 10
}
$pol = Join-Path $env:TEMP "triage-secret-policy.json"
Set-Content -Path $pol -Encoding ascii -Value ('{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"' + $SECRET_ARN + '"}]}')
AwsOk iam put-role-policy --role-name $ROLE --policy-name read-triage-secret --policy-document "file://$pol" | Out-Null
Remove-Item $trust, $pol
$ROLE_ARN = "arn:aws:iam::${ACCOUNT}:role/$ROLE"
AwsTry iam create-service-linked-role --aws-service-name ecs.amazonaws.com | Out-Null  # first-time ECS use

Step "5/9 CloudWatch log group (7-day retention)"
AwsTry logs create-log-group --log-group-name $LOG_GROUP --region $REGION | Out-Null
AwsTry logs put-retention-policy --log-group-name $LOG_GROUP --retention-in-days 7 --region $REGION | Out-Null

Step "6/9 ECS cluster"
AwsOk ecs create-cluster --cluster-name $CLUSTER --region $REGION | Out-Null

Step "7/9 Task definition (0.5 vCPU, 1 GB)"
$envVars = @(
    @{ name = "GROQ_MODEL";          value = (EnvOr "GROQ_MODEL" "openai/gpt-oss-120b") },
    @{ name = "GROQ_FALLBACK_MODEL"; value = (EnvOr "GROQ_FALLBACK_MODEL" "openai/gpt-oss-20b") },
    @{ name = "MIN_RETRIEVAL_SCORE"; value = (EnvOr "MIN_RETRIEVAL_SCORE" "0.35") },
    @{ name = "LLM_TIMEOUT_S";       value = (EnvOr "LLM_TIMEOUT_S" "20") }
)
$hook = EnvOr "TICKETING_WEBHOOK_URL" ""
if ($hook) { $envVars += @{ name = "TICKETING_WEBHOOK_URL"; value = $hook } }
$td = @{
    family = $APP; networkMode = "awsvpc"; requiresCompatibilities = @("FARGATE")
    cpu = "512"; memory = "1024"; executionRoleArn = $ROLE_ARN
    runtimePlatform = @{ cpuArchitecture = "X86_64"; operatingSystemFamily = "LINUX" }
    containerDefinitions = @(@{
        name = "api"; image = $IMAGE; essential = $true
        portMappings = @(@{ containerPort = 8000; protocol = "tcp" })
        environment = $envVars
        secrets = @(
            @{ name = "GROQ_API_KEY";    valueFrom = "${SECRET_ARN}:GROQ_API_KEY::" },
            @{ name = "SERVICE_API_KEY"; valueFrom = "${SECRET_ARN}:SERVICE_API_KEY::" }
        )
        logConfiguration = @{ logDriver = "awslogs"; options = @{
            "awslogs-group" = $LOG_GROUP; "awslogs-region" = $REGION; "awslogs-stream-prefix" = "api" } }
    })
}
$tdFile = Join-Path $env:TEMP "triage-taskdef.json"
Set-Content -Path $tdFile -Encoding ascii -Value ($td | ConvertTo-Json -Depth 10)
$TD_ARN = AwsOk ecs register-task-definition --cli-input-json "file://$tdFile" --region $REGION --query "taskDefinition.taskDefinitionArn" --output text
Remove-Item $tdFile
Write-Host "Task definition: $TD_ARN"

Step "8/9 Network: default VPC + security group (port 8000 open)"
$VPC = AwsOk ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $REGION
if (-not $VPC -or $VPC -eq "None") {
    AwsOk ec2 create-default-vpc --region $REGION | Out-Null
    $VPC = AwsOk ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $REGION
}
$SUBNETS = ((AwsOk ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC" --query "Subnets[].SubnetId" --output text --region $REGION) -split "\s+" | Where-Object { $_ }) -join ","
$SG = AwsTry ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC" --query "SecurityGroups[0].GroupId" --output text --region $REGION
if (-not $SG -or $SG -eq "None") {
    $SG = AwsOk ec2 create-security-group --group-name $SG_NAME --description "Triage Copilot API port 8000" --vpc-id $VPC --query GroupId --output text --region $REGION
    AwsOk ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 8000 --cidr "0.0.0.0/0" --region $REGION | Out-Null
}
Write-Host "VPC $VPC  subnets $SUBNETS  sg $SG"

Step "9/9 ECS service (1 task, public IP, no load balancer)"
$exists = AwsTry ecs describe-services --cluster $CLUSTER --services $SERVICE --region $REGION --query "services[?status=='ACTIVE'].serviceName" --output text
if ($exists) {
    AwsOk ecs update-service --cluster $CLUSTER --service $SERVICE --task-definition $TD_ARN --desired-count 1 --force-new-deployment --region $REGION | Out-Null
} else {
    AwsOk ecs create-service --cluster $CLUSTER --service-name $SERVICE --task-definition $TD_ARN --desired-count 1 `
        --launch-type FARGATE --region $REGION `
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" | Out-Null
}
Write-Host "Waiting for the service to become stable (usually 2-5 min)..."
aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --region $REGION
if ($LASTEXITCODE -ne 0) { Fail "service did not stabilise. Check logs:  aws logs tail $LOG_GROUP --since 15m --region $REGION" }
Show-Url
