# Daily snapshot: pull ^SPX + SPY underlying + option chain, then re-check quality.
# Run from E:\quant_lab. Designed to be wired up to Windows Task Scheduler
# (see scripts/install_daily_task.ps1).
#
# Exit codes:
#   0  - all symbols fetched and quality-checked without errors
#   1  - at least one fetch failed (data NOT written by the fetch scripts when
#        quality checks raise errors — they refuse to corrupt the store)
#
# Logs: data/logs/daily_<timestamp>.log

# Note: we deliberately DO NOT set $ErrorActionPreference = "Stop" here.
# Python's logging goes to stderr, and PowerShell treats native-command stderr
# output as ErrorRecord under Stop, which would abort on the first INFO line.
# Instead we rely on $LASTEXITCODE per step.
$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "data\logs"

if (-not (Test-Path $python)) {
    Write-Host "ERROR: venv python not found at $python" -ForegroundColor Red
    Write-Host "Run scripts\setup_env.ps1 first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logFile = Join-Path $logDir "daily_$ts.log"

$symbols = @("^SPX", "SPY", "QQQ")
$maxExpiries = 12
$failed = @()

function Write-LogLine {
    param([string]$Line)
    # Force UTF-8 (no BOM) for every append. Tee-Object on Windows PowerShell
    # 5.1 has no -Encoding parameter and defaults to UTF-16 LE, which would
    # mix encodings inside a single log file. Add-Content -Encoding utf8 is
    # consistent across PS 5.1 and 7+.
    Add-Content -Path $logFile -Value $Line -Encoding utf8
}

function Invoke-Step {
    param([string]$Label, [string[]]$ArgList)
    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    Write-LogLine "==> $Label  ($(Get-Date -Format o))"

    # Merge stderr->stdout, render any ErrorRecord objects as plain strings so
    # they don't trigger "NativeCommandError" rendering, then write each line
    # to both the log file (UTF-8) and the console.
    & $python @ArgList 2>&1 | ForEach-Object {
        $line = if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.Exception.Message
        } else {
            $_.ToString()
        }
        Write-LogLine $line
        Write-Host $line
    }

    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "    FAILED ($code)" -ForegroundColor Red
        Write-LogLine "    FAILED ($code)"
        return $false
    }
    return $true
}

Write-Host "Daily snapshot starting at $(Get-Date)" -ForegroundColor Green
Write-Host "log: $logFile"

foreach ($sym in $symbols) {
    $okUnd = Invoke-Step "$sym  underlying" @(
        (Join-Path $repoRoot "scripts\fetch_underlying.py"),
        "--symbol", $sym
    )
    if (-not $okUnd) { $failed += "$sym underlying" }

    $okOpt = Invoke-Step "$sym  option chain (max $maxExpiries expiries)" @(
        (Join-Path $repoRoot "scripts\fetch_option_chain.py"),
        "--symbol", $sym,
        "--max-expiries", "$maxExpiries"
    )
    if (-not $okOpt) { $failed += "$sym option chain" }

    $okQc = Invoke-Step "$sym  quality check" @(
        (Join-Path $repoRoot "scripts\check_quality.py"),
        "--symbol", $sym
    )
    if (-not $okQc) { $failed += "$sym quality check" }
}

if ($failed.Count -eq 0) {
    $okPost = Invoke-Step "postprocess  terminal + trinity (incremental)" @(
        (Join-Path $repoRoot "scripts\daily_postprocess.py")
    )
    if (-not $okPost) { $failed += "postprocess" }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "Daily snapshot OK at $(Get-Date)" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Daily snapshot FAILED steps: $($failed -join ', ')" -ForegroundColor Red
    Write-Host "See $logFile for details."
    exit 1
}
