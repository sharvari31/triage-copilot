# Start the container again. NOTE: the public IP changes every start. Run from project root.
. "$PSScriptRoot\common.ps1"
aws ecs update-service --cluster $CLUSTER --service $SERVICE --desired-count 1 --region $REGION --query "service.desiredCount" --output text
Write-Host "Starting (2-4 min)..."
aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --region $REGION
Show-Url
