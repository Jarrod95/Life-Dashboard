param([switch]$Foreground)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run scripts\Setup.ps1 first.' }
$data = Join-Path $root 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$pidFile = Join-Path $data 'dashboard-process.json'
if (Test-Path $pidFile) {
  & (Join-Path $PSScriptRoot 'Status-Dashboard.ps1') -Quiet
  if ($LASTEXITCODE -eq 0) { Write-Host 'Life-Dashboard is already running.'; exit 0 }
  Remove-Item $pidFile -Force
}
$port = if ($env:LIFE_PORT) { [int]$env:LIFE_PORT } else { 5050 }
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port $port is already occupied. No other process was stopped." }
Write-Host "Gym Day import runs automatically when the dashboard starts (when an export directory is configured)."
if ($Foreground) {
  Push-Location $root
  try { & $python (Join-Path $root 'run.py') } finally { Pop-Location }
  exit $LASTEXITCODE
}
$stdout = Join-Path $data 'dashboard.stdout.log'
$stderr = Join-Path $data 'dashboard.stderr.log'
$p = Start-Process -FilePath $python -ArgumentList @((Join-Path $root 'run.py')) -WorkingDirectory $root -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden
@{pid=$p.Id;python=$python;script=(Join-Path $root 'run.py');port=$port;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content $pidFile
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot 'Status-Dashboard.ps1')
