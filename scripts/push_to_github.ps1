# One-time: create private repo and push to GitHub.
# Prerequisite: gh auth login (browser device flow)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Gh = "C:\Program Files\GitHub CLI\gh.exe"
$Git = "C:\Program Files\Git\bin\git.exe"

if (-not (Test-Path $Gh)) {
    Write-Error "GitHub CLI not found. Install: winget install GitHub.cli"
}

& $Gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Log in to GitHub first (browser will open):" -ForegroundColor Yellow
    & $Gh auth login --hostname github.com --git-protocol https --web
}

Push-Location $Root
try {
    $remote = & $Git remote get-url origin 2>$null
    if (-not $remote) {
        & $Git remote add origin https://github.com/wlin050407/quant_lab.git
    }

    $repoExists = & $Gh repo view wlin050407/quant_lab 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating private repo wlin050407/quant_lab ..." -ForegroundColor Cyan
        & $Gh repo create wlin050407/quant_lab --private --source=. --remote=origin --description "SPX 0DTE positioning research terminal"
    }

    Write-Host "Pushing main ..." -ForegroundColor Cyan
    & $Git push -u origin main
    Write-Host "Done: https://github.com/wlin050407/quant_lab" -ForegroundColor Green
}
finally {
    Pop-Location
}
