# Deploy Quantlab Terminal to Railway
# 1) Opens browser login if needed
# 2) Sets ThetaData + basic-auth env vars from local creds
# 3) `railway up` via Dockerfile

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Push-Location $Root
try {
    railway whoami 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Log in to Railway (browser)..." -ForegroundColor Yellow
        railway login
    }

    & .\.venv\Scripts\python.exe scripts\deploy_railway.py
    if ($LASTEXITCODE -eq 0 -and (Test-Path .railway-deploy.local)) {
        Write-Host "`n--- saved credentials ---" -ForegroundColor Green
        Get-Content .railway-deploy.local
    }
}
finally {
    Pop-Location
}
