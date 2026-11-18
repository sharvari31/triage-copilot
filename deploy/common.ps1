# Shared settings + helpers for the deploy scripts.
$REGION      = "ap-south-1"
$APP         = "triage-copilot"
$CLUSTER     = "triage-copilot"
$SERVICE     = "triage-api"
$ROLE        = "triage-copilot-exec-role"
$SECRET_NAME = "triage-copilot/prod"
$LOG_GROUP   = "/ecs/triage-copilot"
$SG_NAME     = "triage-copilot-sg"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "`nFAILED: $m" -ForegroundColor Red; exit 1 }

# Run aws, stop the script on error.
function AwsOk {
    $out = & aws @args 2>&1
    if ($LASTEXITCODE -ne 0) { Fail ("aws " + ($args -join " ") + "`n" + ($out | Out-String)) }
    return ($out | Out-String).Trim()
}
# Run aws, return $null on error (used for "does it exist?" checks).
function AwsTry {
    $out = & aws @args 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $s = ($out | Out-String).Trim()
    if ($s -eq "" -or $s -eq "None") { return $null }
    return $s
}

function EnvVal($name) {
    if (-not (Test-Path .env)) { Fail ".env not found. Run this from the project folder." }
    $line = Get-Content .env | Select-String "^$name="
    if (-not $line) { Fail "$name missing in .env" }
    $v = ($line.Line -split "=", 2)[1].Trim()
    if (-not $v) { Fail "$name is empty in .env" }
    return $v
}
function EnvOr($name, $default) {
    $line = Get-Content .env -ErrorAction SilentlyContinue | Select-String "^$name="
    if ($line) { $v = ($line.Line -split "=", 2)[1].Trim(); if ($v) { return $v } }
    return $default
}

function Show-Url {
    $task = AwsTry ecs list-tasks --cluster $CLUSTER --service-name $SERVICE --desired-status RUNNING --query "taskArns[0]" --output text --region $REGION
    if (-not $task) { Write-Host "No running task. Start it with: powershell -ExecutionPolicy Bypass -File deploy\start.ps1"; return }
    $eni = AwsOk ecs describe-tasks --cluster $CLUSTER --tasks $task --region $REGION --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" --output text
    $ip = AwsOk ec2 describe-network-interfaces --network-interface-ids $eni --region $REGION --query "NetworkInterfaces[0].Association.PublicIp" --output text
    $url = "http://${ip}:8000"
    Set-Content -Path "$PSScriptRoot\last-url.txt" -Value $url -Encoding ascii
    Write-Host "`nLIVE URL: $url" -ForegroundColor Green
    try { Invoke-RestMethod "$url/health" -TimeoutSec 15 | ConvertTo-Json } catch { Write-Host "Health check not answering yet; retry in 30s: Invoke-RestMethod $url/health" }
    Write-Host "Docs: $url/docs"
}
