# MyFitnessPal temporary CSV analytics

This is a read-only temporary workaround until an authorised MyFitnessPal integration is available. It uses the **local** CSVs already saved in `sandbox-scripts/fitness_health/myfitnesspal/data`; no account credentials or private data are copied into Life-Dashboard or fetched from GitHub at runtime.

## Configure
The default local path is `%USERPROFILE%\\OneDrive\\Documents\\Codebases\\sandbox-scripts\\fitness_health\\myfitnesspal\\data`. For a different checkout location, add this to the Life-Dashboard root `.env`:

```dotenv
LIFE_MFP_DATA_DIR=C:\\Users\\jarro\\OneDrive\\Documents\\Codebases\\sandbox-scripts\\fitness_health\\myfitnesspal\\data
```

The app factory reads the variable on startup. Source CSVs are loaded on first request, then cached by path, modification timestamp and size, so changing a CSV refreshes the data on the next request. No manual import command, database migration or extra Python package is required.

## Pages
- `/fitness/weight`: weight metrics, daily history, 7-observation rolling mean (not calendar-day interpolation), monthly weight summaries and sortable history.
- `/fitness/food-diary`: logged-day calories/macros, meal calories, top foods, filtered and paginated individual entries, sorting and CSV download.

Both pages offer year/month/custom date filters and use the existing Solarized light/dark variables. Charts are native canvas, responsive and keyboard-inspectable. Tables use local column sorting. Food entry search and meal filters apply to the **food entries section only**; overview daily charts continue to show the date-filtered full diet.

## Source schema verified from sandbox-scripts
- `myfitnesspal_weight_history.csv`: `date,weight_kg`
- `mfp_2026_apr_oct_daily.csv`: daily calories, macros, sodium, sugar, goal, remaining, entry count, validation fields.
- `mfp_2026_apr_oct_foods.csv`: date, meal, food, entry ID, calories, macros, sodium and sugar.
- `mfp_2026_apr_oct_meals.csv`: date, meal and nutrition totals.

**Missing food logs are not assumed to equal zero intake.** Average calories/macros use days with at least one logged food entry. As source coverage is currently labelled April to October 2026, missing dates outside that span are not inferred. Calories are recorded intake, not net energy balance unless source provides valid exercise adjustments.

## Validate locally
```powershell
python -m pytest tests/test_mfp.py -q
.\\scripts\\Stop-Dashboard.ps1
.\\scripts\\Start-Dashboard.ps1
```

Check both URLs after restarting. No GitHub Actions are needed. The GitHub connector cannot execute Windows browser smoke tests, so production behaviour must be verified locally. The food table is paged at 100 rows (maximum 200); CSV export captures the *displayed current page*, not all matching pages.
