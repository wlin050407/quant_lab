# Bootstrap a local venv and install everything.
# Run from E:\quant_lab.

$ErrorActionPreference = "Stop"

Write-Host "==> Creating venv..." -ForegroundColor Cyan
python -m venv .venv

Write-Host "==> Activating venv..." -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

Write-Host "==> Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "==> Installing requirements..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "==> Installing quant_lab in editable mode..." -ForegroundColor Cyan
pip install -e .

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created .env from .env.example — paste API keys there." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Running tests (offline, mocked)..." -ForegroundColor Cyan
pytest

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  python scripts/fetch_underlying.py --symbol ^GSPC"
Write-Host "  python scripts/fetch_option_chain.py --symbol ^GSPC --max-expiries 6"
Write-Host "  python scripts/check_quality.py --symbol ^GSPC"
