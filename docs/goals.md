# Fitness goals
The /goals page supports body composition, 11 allowlisted exercises and manual body measurements. Configure real targets; no illustrative numbers are seeded. Each edit creates a Goal and GoalVersion; closure freezes the previous target, baseline, latest observation, completion and initial/current forecast. Pause closes a version; configure a new one to resume.

Sources are pinned. Manual and Evolt lean mass use estimated fat-free mass; DEXA lean tissue uses Lean Mass and FFMI uses Total Mass minus Fat Mass with user-entered height. GymDay matching uses allowlisted names and user-selected immutable ID; load goals use completed sets at minimum reps. Confirm dumbbell recording convention. Unweighted pull-ups require explicitly recorded zero load.

Dashboard ideal import recognises explicit measurement and ideal headers; actual current workbook unavailable during development, so verify live layout. Manual targets work regardless. Sync does not overwrite saved goals.

Forecast uses median pairwise slopes in a metric-specific window with freshness and sample checks and a one-year horizon. Ranges are illustrative pace sensitivity. Completion is baseline-adjusted and equal category weighting excludes missing values.

Deploy: stop dashboard, backup database, pull main, run flask --app run db upgrade, pytest, force sync body_composition_workbook and gymday_latest_zip, start dashboard. Existing create_all supports clean databases; migration is idempotent. Legacy goal rows remain preserved but are not automatically migrated without known source/baseline.
