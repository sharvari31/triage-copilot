# Delete EVERYTHING this project created in AWS (after the demo). Run from project root.
. "$PSScriptRoot\common.ps1"
$ok = Read-Host "Type DELETE to remove the service, cluster, image repo, secret, logs, role and security group"
if ($ok -ne "DELETE") { Write-Host "Cancelled."; exit 0 }
aws ecs update-service --cluster $CLUSTER --service $SERVICE --desired-count 0 --region $REGION | Out-Null
aws ecs delete-service --cluster $CLUSTER --service $SERVICE --force --region $REGION | Out-Null
Write-Host "Waiting for tasks to stop..."; Start-Sleep 60
aws ecs delete-cluster --cluster $CLUSTER --region $REGION | Out-Null
aws ecr delete-repository --repository-name $APP --force --region $REGION | Out-Null
aws secretsmanager delete-secret --secret-id $SECRET_NAME --force-delete-without-recovery --region $REGION | Out-Null
aws logs delete-log-group --log-group-name $LOG_GROUP --region $REGION | Out-Null
aws iam delete-role-policy --role-name $ROLE --policy-name read-triage-secret | Out-Null
aws iam detach-role-policy --role-name $ROLE --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" | Out-Null
aws iam delete-role --role-name $ROLE | Out-Null
$sg = aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" --query "SecurityGroups[0].GroupId" --output text --region $REGION
if ($sg -and $sg -ne "None") { aws ec2 delete-security-group --group-id $sg --region $REGION }
Write-Host "Done. Finally, delete the deployer user's access key in the IAM console."
