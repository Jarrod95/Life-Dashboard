$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $Root
try {
  $Python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
  & $Python -m pytest tests/test_gymday.py -q
  if ($LASTEXITCODE -ne 0) { throw 'Gym Day tests failed.' }
} finally { Pop-Location }
