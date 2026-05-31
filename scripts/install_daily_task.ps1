# Register (or update) a Windows Scheduled Task that runs daily_snapshot.ps1
# every weekday at 16:35 local time.
#
# Why 16:35: SPX/SPY cash session closes 16:00 ET. yfinance EoD chains and OI
# settlement values usually populate within 20–30 min. Adjust if your local
# time != ET.
#
# Run this script ONCE manually (in an elevated or normal PowerShell — task is
# created under the current user). It's idempotent: re-running updates the task.
#
# To uninstall:  Unregister-ScheduledTask -TaskName "quant_lab.daily_snapshot" -Confirm:$false

$ErrorActionPreference = "Stop"

$taskName = "quant_lab.daily_snapshot"
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\daily_snapshot.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: $scriptPath not found" -ForegroundColor Red
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "16:35"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# Note on -WakeToRun: lets Windows pull the machine out of sleep at 16:35
# to run the fetch. Requires:
#   1. Laptop plugged into AC (battery mode disables wake timers by default).
#   2. Control Panel -> Power Options -> Advanced -> Sleep -> "Allow wake
#      timers" = Enabled (Windows default is Enabled).
# After the task finishes, Windows returns to sleep per the usual power
# plan idle timeout (no shutdown, no permanent wake).

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Updating existing task '$taskName'..." -ForegroundColor Cyan
    Set-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings | Out-Null
} else {
    Write-Host "Registering new task '$taskName'..." -ForegroundColor Cyan
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "quant_lab daily option-chain snapshot of ^SPX + SPY + QQQ, then terminal/trinity refresh" | Out-Null
}

Write-Host ""
Write-Host "Task '$taskName' installed." -ForegroundColor Green
Write-Host "  next run:    Weekdays 16:35 local time"
Write-Host "  script:      $scriptPath"
Write-Host "  log dir:     $repoRoot\data\logs"
Write-Host ""
Write-Host "To run once manually now:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "To check status:"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$taskName'"
