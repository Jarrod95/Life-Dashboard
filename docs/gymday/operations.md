# Gym Day strength analytics

## Setup and operations
Set `LIFE_GYMDAY_EXPORT_DIR` in your local `.env` (never commit that file) to the directory containing Gym Day `.zip` exports. Optionally set `LIFE_GYMDAY_IMPORT_ON_STARTUP=true`. No private ZIP is written into the repository, and imported data remains on your own SQLite database.

Launch the existing dashboard with `./scripts/Start-Dashboard.ps1` and visit `/fitness/strength`. Use **Data & sync → Refresh from latest export** after downloading a new export. The refresh uses the application's existing CSRF protection. If a ZIP is corrupt, the importer reports that error and can fall back to the next valid archive, surfacing the rejected filename.

From a PowerShell terminal:

```powershell
.\scripts\Import-GymDay.ps1
.\scripts\Test-GymDay.ps1
```

Existing finance tables and URLs are not intentionally modified. The existing Flask factory creates newly registered SQLAlchemy tables during startup; for production deployments, introduce an Alembic revision instead of relying on automatic schema creation.

## Source mapping and audit

Source filenames used: `WorkoutSession.json`, `WorkoutSessionExercise.json`, `WorkoutSessionSet.json`, `Exercise.json`. Exercises and sets nested in each session take precedence over their flattened companions. UUIDs are retained as primary keys; repeated imports upsert stable records instead of duplicating. Dates are epoch milliseconds in the ZIP and interpreted as UTC instants before Sydney-local date filtering. Invalid durations are null rather than zero.

Other fields included: workout/session name, position, exercise category, equipment, primary/secondary muscle names, set ordinal, reps, weight, measurement unit, source 1RM, complete/warmup/drop/failure status. Unknown units do not receive a guessed kg conversion. ZIPs are read in memory, not extracted to disk; member paths, CRC and decompressed sizes are checked.

**Unverified against a real Gym Day ZIP:** the source ZIP was not available in this implementation environment. The reference specification reports 776 raw session entities, 5,586 raw exercise-session entities, 20,072 raw set entities, and 816 exercises for the 21 October 2026 export. These have not been reconciled. Numeric measurement unit encodings, custom exercise categories and nested-versus-flat relationship completeness need checking using the actual archive before declaring production readiness. Data can be incomplete if a source uses unfamiliar relationship structures.

## Metric definitions

- Sessions are distinct active saved session UUIDs in the Sydney-local filter window. Training days are distinct Sydney dates.
- Duration is end minus start, only if both dates exist and the difference is non-negative.
- Working sets are completed sets excluding warm-ups. All other logged sets remain visible in session detail.
- Reps are the total recorded reps in completed working sets.
- Tonnage is the sum of canonical kilograms × reps for completed non-warmup sets with usable weight and reps. This is *logged external load × reps*, not physical work; bodyweight and unknown units are not inferred.
- Estimated 1RM is measured load for one rep and Epley `weight × (1 + reps/30)` for 2–10 reps, with missing or invalid loads omitted.
- Primary/secondary muscle attributions give full credit to each listed muscle. These category totals can exceed the number of unique working sets.
- Frequency buckets are ISO weeks (Monday to Sunday). Weekly volume is aggregated by session's Sydney-local date.
- PR history records strict estimated-1RM improvements in timestamp order; ties are not new PRs.

## Known implementation gaps

This is an initial functional release, **not full completion of the supplied specification**. The HTML views have filters, native interactive browser charts and API pagination for sessions/exercises/sets; additional work is needed for year-over-year comparisons, multi-metric PR categories, donut visualisation, day-by-day month calendar, crossfilter by exercise/muscle in all KPIs, progress regression, advanced sort/CSV on every table, browser accessibility verification, large-file performance profiling and an explicit Alembic migration. The exercise/record views currently expose a smaller set of dimensions than the full spec.

## Verification
Run `python -m pytest tests/test_gymday.py -q` locally; synthetic tests cover deterministic archive discovery, milliseconds, idempotency, working set maths, filtering and corrupt newest ZIP fallback. **The tests have not been executed in this GitHub-connector environment**, which does not have a local checkout of this branch. Do not mark this PR ready to merge without running tests and reconciling the actual export.

## Automatic import on dashboard launch

The application factory loads the repository-root `.env` before reading configuration. Set `LIFE_GYMDAY_EXPORT_DIR` to the folder containing your downloaded Gym Day ZIP archives. **No separate import command is required.** The dashboard imports the latest valid ZIP when it launches, by default whenever this directory is configured. Set `LIFE_GYMDAY_IMPORT_ON_STARTUP=false` only to turn this off. The importer checks SHA-256 and importer version to avoid unnecessary reimports. A failed startup import logs an error and retains existing data without taking finance routes offline.

The supplied October 21, 2026 ZIP was examined in this change: 776 nested sessions, 5,586 nested session exercises, and 20,072 nested sets, matching flattened source counts, each with unique IDs. It includes 19,541 set units of `kg`, 99 of `km`, and 432 with missing units. `km` and missing units must not be interpreted as lifting kilograms. Source export itself is excluded from version control.

Use `./scripts/Start-Dashboard.ps1` to launch normally. The local server's default port is **5050**, so open `http://127.0.0.1:5050/fitness/strength`. Restart the process after downloading a new ZIP to trigger discovery/import, or use the existing Data & sync page's manual browser refresh as an optional alternative.
