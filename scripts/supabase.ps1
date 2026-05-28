param(
  [switch]$Start,
  [switch]$Stop,
  [switch]$Status,
  [switch]$WriteEnv
)

$ErrorActionPreference = "Stop"

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: '$name'. Install it and re-run."
  }
}

Assert-Command docker
Assert-Command supabase

function Write-EnvFromSupabaseStatus {
  $envLines = & supabase status -o env 2>$null
  if (-not $envLines) {
    throw "Could not read env from 'supabase status'. Is Supabase running?"
  }

  $pairs = @{}
  foreach ($line in $envLines) {
    if ($line -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$") {
      $pairs[$matches[1]] = $matches[2]
    }
  }

  if (-not $pairs["SUPABASE_URL"] -or -not $pairs["SUPABASE_ANON_KEY"]) {
    throw "Expected SUPABASE_URL and SUPABASE_ANON_KEY from 'supabase status -o env'."
  }

  $envPath = Join-Path (Get-Location) ".env"
  $existing = @{}
  if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
      if ($line -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$") {
        $existing[$matches[1]] = $matches[2]
      }
    }
  }

  $existing["SUPABASE_URL"] = $pairs["SUPABASE_URL"]
  # Repo uses SUPABASE_KEY; Supabase CLI prints SUPABASE_ANON_KEY.
  $existing["SUPABASE_KEY"] = $pairs["SUPABASE_ANON_KEY"]

  $out = $existing.Keys | Sort-Object | ForEach-Object { "$_=$($existing[$_])" }
  Set-Content -Path $envPath -Value $out -Encoding UTF8

  Write-Host "Wrote .env with SUPABASE_URL + SUPABASE_KEY (anon key)."
}

if (-not ($Start -or $Stop -or $Status -or $WriteEnv)) {
  Write-Host "Usage:"
  Write-Host "  .\scripts\supabase.ps1 -Start"
  Write-Host "  .\scripts\supabase.ps1 -Stop"
  Write-Host "  .\scripts\supabase.ps1 -Status"
  Write-Host "  .\scripts\supabase.ps1 -WriteEnv"
  exit 1
}

if ($Start) {
  & supabase start
  Write-EnvFromSupabaseStatus
}

if ($Stop) {
  & supabase stop
}

if ($Status) {
  & supabase status
}

if ($WriteEnv) {
  Write-EnvFromSupabaseStatus
}

