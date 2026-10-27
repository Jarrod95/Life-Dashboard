$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    py -3.12 -m venv (Join-Path $root '.venv')
  }
  $python = Join-Path $root '.venv\Scripts\python.exe'
  & $python -m pip install --upgrade pip
  & $python -m pip install -e '.[dev]'
  if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
  }
  New-Item -ItemType Directory -Force -Path (Join-Path $root 'data') | Out-Null
  Write-Host "Setup complete. Edit .env, then run .\scripts\Start-Dashboard.ps1"
} finally { Pop-Location }
