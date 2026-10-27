param([int]$Keep=10)
$ErrorActionPreference='Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$path = Join-Path $root 'data\life-dashboard.sqlite'
$backupDir = Join-Path $root 'data\backups'
if (-not (Test-Path $path)) { throw 'Database does not exist.' }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$dest = Join-Path $backupDir ("life-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.sqlite')
$script = 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()'
& $python -c $script $path $dest
if ($LASTEXITCODE -ne 0) { throw 'SQLite backup failed' }
Get-ChildItem $backupDir -Filter 'life-*.sqlite' | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | Remove-Item -Force
Write-Host "Backup created: $dest"
