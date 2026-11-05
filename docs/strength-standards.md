# Strength Standards

The **Strength Standards** tab at /fitness/strength/standards compares Gym Day working-set 1RM with permitted OpenProgression barbell benchmarks. It is an informational training aid, **not** a clinical assessment, population percentile, competitive qualification or proof of lifting technique.

## Prerequisites and explicit configuration

Existing data sources: imported Gym Day workouts, the cached MyFitnessPal weight-history CSV (local or OneDrive cache) and stored **manual** body-composition weights. Nothing is uploaded to the benchmark provider.

The visible **Benchmark reference** selector offers male and female source tables. The UI currently opens on the **male** reference for this personal dashboard; change it using the dropdown if inappropriate. This is a visible starting choice, **not inferred from workouts or biometric data**. APIs accept an explicit `sex=male|female` query; the older `LIFE_STRENGTH_STANDARD_SEX` private .env setting remains a fallback for direct API requests. If neither the query parameter nor the environment value is set, an API request fails closed with `configuration_required` instead of guessing. Only two benchmark categories exist upstream.

`config/strength-exercise-mapping.yaml` contains narrowly approved **exact-name aliases** for the screenshot-confirmed Gym Day barbell names (Barbell Bench Press, Barbell Squat, Barbell Deadlifts, and canonical variants). This resolves immutable Gym Day IDs at runtime without guessing private UUIDs. An explicit ID entry takes precedence, including `approved: false` to block an alias. A known non-barbell equipment field vetoes the alias. Review whether each exported load includes the bar before relying on that rating.

### Inspect exercise IDs and approve exact mappings

1. Refresh Gym Day via Strength training → Data & sync.
2. Inspect the read-only endpoint:

~~~powershell
(Invoke-RestMethod "http://127.0.0.1:5050/api/v1/fitness/strength/standards/exercises?window=all_time").data |
    Select-Object id,name,equipment,eligible_sessions,movement,rated
~~~

3. Confirm the **exact** imported Gym Day ID, equipment and load convention for a specific movement. The only supported categories are barbell back/front/overhead squat, flat barbell bench press, standing strict overhead press and conventional barbell deadlift. Name aliases must match the *whole approved name*, never fuzzy or substring match. Do not substitute RDLs, JM presses, Bulgarian split squats, belt squats, machines, or other movements.
4. In config/strength-exercise-mapping.yaml, use the verified actual exercise ID, the corresponding upstream movement ID and the fields below (the UUID shown is **illustrative only**, never a live default):

~~~yaml
mappings:
  "00000000-0000-4000-8000-000000000000":
    movement: back_squat
    benchmark_provider: openprogression
    load_convention: total_barbell_kg
    approved: true
~~~

5. Restart locally and confirm ratings. Total barbell weight means **bar included**. RDL, leg press, hack squat, hip thrust, machines, Smith/dumbbell presses, weighted bodyweight movements etc. remain **Unrated / Ratio only**. Those movements cannot borrow a different exercise's standards. There is no unauthenticated mapping write API. The table defaults to **rated exercise rows only** to avoid an ocean of empty columns; tick **Show unrated exercises** for ratios and explicit “Not benchmarked” cells for unsupported variants. The CSV still includes all rows.

## Source, version and licence

**Provider:** [OpenProgression](https://github.com/OpenProgression/openprogression) benchmark dataset **1.0.0**, MIT License, Copyright (c) 2026 OpenProgression.

**Pinned upstream commit:** 1e9ead0019bd064e263fa0e42e583c66d9f06c6e. Verified/retrieved: 2026-11-05.

| Upstream source | Git blob SHA-1 |
|---|---|
| data/benchmarks/squatting.json | bf577b28f85e7407b485fe20f413a6b57b3f6c8b |
| data/benchmarks/pressing.json | 6d7255b649296e093a2a9c429fb7f9ffc6273e33 |
| data/benchmarks/pulling.json | 8bedae049e71b989b440f2f6213335df8dd92656 |

The vendored subset is config/strength-standards/openprogression-v1.0.0.json (Git blob SHA-1: 666475c049f989700409fa3863fbd1074dd7193a). It retains the six verified source movement identifiers, source citation keys, original seven level names, bodyweight multipliers, test type and units; it omits unrelated absolute-kg standards, descriptions and notes. Version, pinned upstream commit, URL and content hashes are recorded in the JSON. The integrity regression test verifies the repository's Git blob hash **after normalising only Windows CRLF line endings to LF**, since Git's checkout conversion changes local bytes without changing benchmark content. It continues to reject any modified threshold or other JSON content. The complete MIT notice is in config/strength-standards/LICENSE-OPENPROGRESSION.txt. To update: fetch the exact upstream revision, verify source blob hashes and MIT licence, rebuild a minimal subset by the stated transform, inspect differences and rerun the benchmark tests. Changes need a separate reviewed PR; there are no runtime source downloads.

**Simplified dashboard labels:**

| OpenProgression source | Dashboard |
|---|---|
| Below intermediate, including beginner tiers | Developing |
| intermediate / intermediate_plus | Good |
| advanced / advanced_plus | Excellent |
| rx | Elite |

The milestone thresholds are inclusive: bodyweight multiplied by intermediate, advanced or rx respectively. Exact unrounded numbers determine status; display rounding occurs only afterward. Source tiers do **not** imply percentages of the general gym-going population, and strength across unrelated exercises is not directly rankable. E.g. a *synthetic* 87 kg male back squatting 150 kg × 5 has Epley e1RM of 175 kg, ratio 2.01× BW and the simplified category Excellent; the Elite milestone is 195.75 kg.

**Strength Level** source data, percentiles, ratios and model outputs are **not** copied, scraped, approximated or derived. Its [data licence policy](https://strengthlevel.com/data-licensing) requires written permission to reuse them. An authorised future licensed provider would require its own source-specific ingestion, version and category controls; attribution alone is insufficient.

## Metric and bodyweight definitions

Only active sessions and completed non-warmup sets with canonical finite kg > 0 and **whole reps 1–10** are scored. A single actual rep is labelled **observed 1RM**. For two through ten reps, use the existing Gym Day Epley calculation: kg × (1 + reps/30), labelled **estimated 1RM**. Complete drop sets count; source_onerm is never presented as a direct observation. Choose the **highest actually lifted kg** from eligible sets per session, then the heaviest recorded set in the selected period. Break ties by highest calculated e1RM, then newest workout date, session ID and set ID. The dashboard clearly labels the computed number **e1RM from heaviest set**: a lighter ten-rep set can have a larger Epley estimate, but does not override the requested heaviest-weight selection. Preserve actual set, date, load, reps and observed/estimated provenance.

**Current summary:** default is the **heaviest qualifying set in the past 90 days**. Optional 365-day and all-time views remain available; the range is applied before choosing the set, and year/month/from/to filters **intersect** with it. A historical all-time maximum is contextual rather than simultaneous with current bodyweight.

**Bodyweight divisor:** take the **highest valid, actually measured bodyweight in the preceding 90 calendar days, inclusive of the as-of date**. Consider MFP and stored manual weight records, with MFP taking precedence for a duplicate *date*. Choose the maximum weight, breaking ties by newest day, then MFP. Ignore future records and exclude Evolt/DEXA mass or forecasts. Return the source, observed date, 90-day interval and method in API/CSV. If the whole 90-day interval lacks a weight, show unavailable and do not fabricate rankings. This deliberate peak-weight divisor is more conservative than the prior newest-within-14-days rule.

**Historical chart:** each completed session uses the highest available bodyweight within the **90 days leading up to its own date**, with no lookahead. It considers MyFitnessPal plus manual CompositionRow observations. An invalid duplicate cannot override an earlier valid measurement; last **valid** row within a source/day wins. No future readings or interpolation. Evolt/DEXA mass is deliberately excluded. Missing historical weight creates a ratio gap while retaining the absolute e1RM data point.

Missing, stale (>90-day) or unavailable weight, absent or invalid API sex choice, unapproved exercise or invalid benchmark yields explicit **no rating** and no fabricated milestone. Status values include rated, unrated_exercise, missing_bodyweight, stale_bodyweight, no_valid_sets, benchmark_unavailable, source_unavailable and configuration_required. MFP parses its existing cached CSV once per API request context; missing CSV falls back to stored manual weights. No future projected bodyweight is used for present ratings.

## Layout and data access

The **Your 1RM | Good | Excellent | Elite** benchmark bars use Solarized accent/blue/contrast-aware green/violet in light and dark modes. Labels appear directly underneath bars, numeric values and tooltips retain **kg**, and there is **no Load legend or bottom-axis title**. An adjacent semantic table mirrors all four values. Hover/focus plus arrow/Home/End support the native canvas interactions. The theme change event and ResizeObserver redraw charts.

**Light:** pale surface and muted grid with theme-token bars. **Dark:** deep blue-green surface, brighter green/violet/blue contrasts and cyan accent. Narrow screens stack cards and horizontally scroll tabular data. Charts do not project future strength.

The sortable/filterable all-exercise table shows source status, exact set, e1RM, ratio, level, milestone, gap and record date. Export CSV is server-generated with spreadsheet formula neutralisation.

### Read-only endpoints

All under /api/v1/fitness/strength/standards:

~~~text
GET /metadata
GET /exercises?window=all_time
GET /summary?exercise_id=<real-id>&window=90d&sex=male
GET /exercises/<real-id>/progress?window=90d&sex=male
GET /comparison?page=1&page_size=100
GET /comparison.csv?year=2026&month=10&window=90d&sex=male
~~~

All JSON endpoints return data + meta or an error envelope. The summary includes period, best_set, bodyweight provenance, relative_strength, classification, benchmarks, next_milestone and status. Filters use Gym Day year/month/from/to intersection. Window values: 90d (default), 365d, all_time. The `sex` query accepts only male or female; the UI shows an editable reference selector. Exercises with no qualifying sets in the window are not preferred as the initial dropdown selection. The current comparison tab shows rated results first and can reveal unsupported exercises with status explanations. Optional as_of=YYYY-MM-DD cannot be later than today's Sydney date; pagination size is 1–200.

**Security:** this existing local-first dashboard does **not** use login auth for its pre-existing Gym Day GET endpoints. These additions preserve that access model and do not claim stronger authentication. Keep the service on localhost or a controlled private network, not publicly exposed. Existing CSRF protections apply to mutating requests and were not changed. No new persistent tables, database mutations, credentials, private archives or personal weight CSVs are added to Git.

## Windows test and manual browser verification

~~~powershell
python -m pytest tests/test_gymday.py tests/test_strength_standards.py tests/test_strength_standards_api.py -q
python -m pytest -q
node --check app/static/js/strength-standards.js
.\scripts\Start-Dashboard.ps1
~~~

Before merging/deploying, confirm light/dark and phone widths 390px/500px, exact four category bars when rated, readable kg values, **no Load legend/axis title**, correct hover/focus and keyboard access, no clipped labels. Change exercises repeatedly and toggle the theme; check tooltips and handlers are not duplicated. Confirm no-data, incomplete mapping, stale weight and missing-file states. Verify Gym Day import, MFP, composition, Records and Exercises remain unaffected, then run the CSV through a spreadsheet to confirm formula injection is neutralised. Verify real Gym Day exercise UUID/equipment and external load conventions against your own imported source before approving it. No production VPS changes are authorised by this feature.
