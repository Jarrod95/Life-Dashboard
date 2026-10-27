$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  $tracked = & git ls-files
  $bad=@($tracked | Where-Object { $_ -match '(?i)(^|/)(data|backups|exports|credentials|secrets)/|(^|/)[^/]+\.(xlsx|xls|sqlite3?|db|pem|key|csv)$|(^|/)\.env$' })
  if ($bad.Count -gt 0) { Write-Error "Sensitive paths tracked by Git: $($bad -join ', ')"; exit 1 }
  Write-Host 'Tracked file path privacy check passed.'
} finally { Pop-Location }
