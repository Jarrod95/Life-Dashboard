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


## Automatic import from .env

On each `python run.py` or `Start-Dashboard.ps1` launch, the server reads
`LIFE_FINANCE_XLSX_PATH` from the repository's local `.env` and imports the
workbook before accepting requests. Example (do not commit the local path):

```dotenv
LIFE_FINANCE_XLSX_PATH=C:\Users\jarro\OneDrive\Documents\Finance & Work\Tracking Spreadsheets\Financial_Dashboard.xlsx
```

An unchanged workbook is detected by SHA-256 and produces no new business rows.
If the path is wrong or OneDrive has not downloaded the workbook, the server logs
the failure and keeps the last successful local database. It does **not** poll
or watch for changes while running; restart to sync new workbook changes.

## Westpac data

A sheet named `Transactions_Westpac_All!` (trailing exclamation optional) is
processed alongside NAB year sheets. Its parser uses column headings, not fixed
positions, and expects Date plus either Amount or both Debit and Credit.
Recognised aliases include Transaction Date, Transaction Description, Account
Name and Category. Westpac account names are prefixed in SQLite so accounts
with the same label as NAB accounts do not collapse together.

Salary/wage/payroll descriptions are treated as income when the signed amount
is positive. Other credits are **not** assumed to be income. Internal transfers
are excluded when explicitly recognisable, but cross-bank counterpart matching
and comprehensive duplicate detection are still outstanding; verify cash flow
and avoid interpreting unclassified transfers as income or expenditure.

**Data validation limitation:** The workbook attached during implementation
did not contain a Westpac sheet, so the real Westpac schema has not yet been
verified. Inspect preview warnings and reconcile transaction counts before
trusting reported income or spending.


### Verified uploaded Westpac layout

The latest uploaded workbook contains `Transactions_Westpac_All` (no trailing exclamation mark), with these eight headers in order: `Bank Account`, `Date`, `Narrative`, `Debit Amount`, `Credit Amount`, `Balance`, `Categories`, `Serial`. Local read-only structure validation found **947 usable rows**, **3 distinct accounts**, **402 credits**, **545 debits**, and **0 structurally rejected rows**. Of the positive rows, 79 contain the explicit string 'salary'. This does *not* certify that every income/transfer classification is correct.

The exporter has been kept out of the repository. For production, ensure the configured `.env` path points to this newer workbook; the upload filename and Windows filename need not match.

Verify after launching: `/settings/imports` should show a new completed import and the transaction explorer should contain Westpac records. If the file was not changed after a previous successful import, SHA-256 will correctly skip it.
