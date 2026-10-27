# Life Dashboard

A local-first personal dashboard built with Flask, Jinja2, SQLite and custom Solarized Light/Dark CSS.

## Windows startup

```powershell
.\scripts\Setup.ps1
.\scripts\Start-Dashboard.ps1
.\scripts\Status-Dashboard.ps1
```

Open http://127.0.0.1:5050. Background start is not automatic startup after reboot.

## Import the financial workbook

```powershell
.\scripts\Import-Finances.ps1 -File "C:\Users\jarro\OneDrive\Documents\Finance & Work\Tracking Spreadsheets\Financial Dashboard.xlsx" -DryRun
.\scripts\Import-Finances.ps1 -File "C:\Users\jarro\OneDrive\Documents\Finance & Work\Tracking Spreadsheets\Financial Dashboard.xlsx"
.\scripts\Test-Dashboard.ps1
.\scripts\Backup-Data.ps1
.\scripts\Stop-Dashboard.ps1
```

The import UI is under Data & imports. Source files are not modified. Real financial figures are **not** included in the repository. Budget formulas, asset reconciliation, and transaction classifications must be validated on the source workbook before being treated as financial truth.

Fitness, Health, and Goals show truthful unconfigured states.

See `docs/architecture.md`, `docs/api.md`, `docs/metrics-definitions.md`, `docs/privacy-and-backups.md` and `docs/development.md`. Do not expose this unauthenticated local server outside loopback.
