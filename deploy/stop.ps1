# Stop the container (stops compute billing; keeps everything else). Run from project root.
. "$PSScriptRoot\common.ps1"
aws ecs update-service --cluster $CLUSTER --service $SERVICE --desired-count 0 --region $REGION --query "service.desiredCount" --output text
Write-Host "Stopped. Costs now ~`$0.50/month (secret + image). Start again: deploy\start.ps1"
