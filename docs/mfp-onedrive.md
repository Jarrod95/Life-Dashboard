# MyFitnessPal exports via Microsoft Graph

Life-Dashboard can import MFP exports from the same personal OneDrive connection as
the finance, body-composition and GymDay sources.

## Configuration

Set in the server's private `.env`:

```dotenv
LIFE_DATA_SOURCE=onedrive
LIFE_MFP_ONEDRIVE_DIR=Documents/Codebases/sandbox-scripts/fitness_health/myfitnesspal/data
MFP_CALORIE_GOAL=1800
MFP_CARB_GOAL=73
MFP_FAT_GOAL=60
MFP_PROTEIN_GOAL=203
```

The Graph path is relative to the **personal OneDrive root**, not to the
local Windows account's `C:\Users\...\OneDrive` directory.

## Required files

The folder must contain food diary CSVs matching `mfp_*_daily.csv`,
`mfp_*_foods.csv`, and `mfp_*_meals.csv`, plus
`myfitnesspal_weight_history.csv`. Additional dated CSV export sets are
supported. Files can overlap: the newer file wins on matching dates,
meal/date pairs or MFP food entry IDs. The `*_full.json` backup is ignored to
avoid double counting its duplicate data.

The four consolidated CSV outputs are written to
`instance/mfp-graph-cache/`. The dashboard reads only this local managed
cache, not Graph on every page request. Existing local mode continues using
`LIFE_MFP_DATA_DIR`.

## Commands

```powershell
python -m flask --app run:app graph-test
python -m flask --app run:app sync-sources --source mfp_exports
python -m flask --app run:app sync-sources --source mfp_exports --force
```

Or use `sync-sources --all` to update every OneDrive source.

Inspect the four file availability flags:

```powershell
Invoke-RestMethod http://127.0.0.1:5051/api/v1/fitness/mfp/status
```

The Graph Data Sources page reports `mfp_exports` sync status and history.
If the configured path is wrong, use the folder browser to select the MFP
directory (the folder selection is persisted by Graph item ID).

## Recovery

A download, invalid CSV, or incomplete export bundle does not overwrite the
last successfully consolidated set. Check the sync run's error code and source
status. On Windows the user signing in to Graph must match the Windows identity
running the dashboard service to access the DPAPI token cache.

**Data caveat:** Daily CSV rows with `food_entries=0` are not treated as
verified zero intake. Daily nutrition averages exclude those unlogged days.

Files contain personal health data and should never be committed to Git.
