# Body composition dashboard

The Life Dashboard reads the body composition workbook **without editing it**. Set `LIFE_BODY_COMPOSITION_XLSX_PATH` in the repository-root `.env` to the actual OneDrive file. Set `LIFE_BODY_COMPOSITION_IMPORT_ON_STARTUP=true` (default) to refresh on every Flask startup. The existing SQLite database stores the last successful snapshot.

The importer reads only four canonical worksheets: `Data`, `Evolt Scans`, `DEXA - General` and `DEXA - Enhanced`. It deliberately never reads or exposes `Cycling`. Evolt and DEXA fraction-based body-fat percentages are normalised to percentage points; the manual and regional percentages are already percentage points. DEXA region grams are also exposed in kilograms as extra derived fields without overwriting their original measurements. The importer validates the entire workbook before replacing rows in one transaction. A corrupt, missing or locked source leaves previous measurements intact.

## Windows validation (no GitHub Actions required)

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
.\scripts\Stop-Dashboard.ps1
.\scripts\Start-Dashboard.ps1 -Foreground
```

Visit `/fitness/body-composition`, its Measurements, Evolt, DEXA, Projections and Data health tabs, and `/`. Confirm the finance graphs remain functional, food-diary bars retain their goal lines and labels are legible in both themes. Refresh and inspect `/static/favicon.svg` (HTTP 200). Verify the four imported row counts against your current source workbook; for the October 2026 snapshot they are approximately 26, 18, 1, 18, respectively.

If import fails, inspect Flask startup logs and the source-status tab. Check that the workbook is available offline through OneDrive and not locked. This PR does not include the private workbook or any actual `.env`.

## Known validation gaps

GitHub Actions were not run. The remote repository could not be cloned into the execution container, so `pytest`, Windows PowerShell restart and manual browser verification **remain to be performed locally** before merge. DEXA history charts will only make sense after a second whole-body scan; the current single scan is a cross-section. Projection envelopes are descriptive, not statistical confidence intervals. The data-health screen shows saved-import state, not live record refresh without a restart.
