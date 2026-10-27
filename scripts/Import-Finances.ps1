param([string]$File, [switch]$DryRun, [switch]$VerboseOutput, [switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run Setup.ps1 first.' }
$argsList = @('-m','app.cli')
if ($File) { $argsList += @('--file', $File) }
if ($DryRun) { $argsList += '--dry-run' }
if ($VerboseOutput) { $argsList += '--verbose' }
if ($Force) { $argsList += '--force' }
Push-Location $root
try { & $python @argsList; if ($LASTEXITCODE -ne 0) { throw 'Import failed' } }
finally { Pop-Location }
