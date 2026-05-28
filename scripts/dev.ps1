param(
  [switch]$Setup,
  [switch]$RunApi,
  [switch]$Test,
  [switch]$Lint
)

$ErrorActionPreference = "Stop"

function Ensure-Venv {
  if (-not (Test-Path ".venv")) {
    python -m venv .venv
  }
  . .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
}

if (-not ($Setup -or $RunApi -or $Test -or $Lint)) {
  Write-Host "Usage:"
  Write-Host "  .\scripts\dev.ps1 -Setup"
  Write-Host "  .\scripts\dev.ps1 -RunApi"
  Write-Host "  .\scripts\dev.ps1 -Test"
  Write-Host "  .\scripts\dev.ps1 -Lint"
  exit 1
}

if ($Setup) {
  Ensure-Venv
  pip install -e ".[dev]"

  if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Update values as needed."
  }

  try {
    & .\scripts\supabase.ps1 -Start | Out-Host
  } catch {
    Write-Host "Supabase local start skipped: $($_.Exception.Message)"
  }
}

if ($RunApi) {
  Ensure-Venv
  uvicorn lpi.main:app --reload --port 8000
}

if ($Test) {
  Ensure-Venv
  pytest -v --tb=short
}

if ($Lint) {
  Ensure-Venv
  ruff check src/ tests/
  mypy src/ --ignore-missing-imports
}

