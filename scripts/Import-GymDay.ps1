$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $Root
try {
  $Python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
  & $Python -c "from app import create_app; from app.gymday import import_latest; app=create_app(); context=app.app_context(); context.push(); print(import_latest()); context.pop()"
  if ($LASTEXITCODE -ne 0) { throw 'Gym Day import failed.' }
} finally { Pop-Location }
