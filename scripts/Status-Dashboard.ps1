param([switch]$Quiet)
$root = Split-Path -Parent $PSScriptRoot
$file = Join-Path $root 'data\dashboard-process.json'
if (-not (Test-Path $file)) { if (-not $Quiet) { Write-Host 'STOPPED (no PID state)' }; exit 1 }
$state = Get-Content $file -Raw | ConvertFrom-Json
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)" -ErrorAction SilentlyContinue
if (-not $proc -or -not $proc.CommandLine -or
    -not $proc.CommandLine.Contains([string]$state.script) -or
    -not $proc.ExecutablePath -or
    -not ([IO.Path]::GetFullPath($proc.ExecutablePath).Equals([IO.Path]::GetFullPath([string]$state.python),[StringComparison]::OrdinalIgnoreCase))) {
  if (-not $Quiet) { Write-Host 'STOPPED (stale/unverified PID)' }; exit 1
}
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($state.port)/health" -TimeoutSec 3
  if ($health.status -ne 'ok') { throw 'Bad health status' }
  if (-not $Quiet) { Write-Host "RUNNING PID $($state.pid) http://127.0.0.1:$($state.port)"; Write-Host "Logs: $(Join-Path $root 'data')" }
  exit 0
} catch { if (-not $Quiet) { Write-Host "UNHEALTHY PID $($state.pid)" }; exit 2 }
