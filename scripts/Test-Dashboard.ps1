$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
Push-Location $root
try {
  & $python -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
  & $python -m ruff check .
  if ($LASTEXITCODE -ne 0) { throw 'ruff failed' }
} finally { Pop-Location }
