$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$file = Join-Path $root 'data\dashboard-process.json'
if (-not (Test-Path $file)) { Write-Host 'Already stopped.'; exit 0 }
$state = Get-Content $file -Raw | ConvertFrom-Json
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)" -ErrorAction SilentlyContinue
if ($proc -and $proc.CommandLine -and $proc.CommandLine.Contains([string]$state.script) -and
    $proc.ExecutablePath -and
    ([IO.Path]::GetFullPath($proc.ExecutablePath).Equals([IO.Path]::GetFullPath([string]$state.python),[StringComparison]::OrdinalIgnoreCase))) {
  Stop-Process -Id $state.pid -ErrorAction Stop
  Write-Host "Stopped verified dashboard PID $($state.pid)."
} else { Write-Host 'Stale/unverified PID; no process terminated.' }
Remove-Item $file -Force
