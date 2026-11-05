# Development and unfinished work

Install Python 3.12+ and `pip install -e '.[dev]'`. Run `python -m pytest -q` and `python -m ruff check .`, then `python run.py`.

The source Excel workbook was not uploaded into this execution environment. Run the dry-run import on Windows first; confirm year counts, snapshot dates, category classification and reported totals.

Outstanding relative to the supplied specification: verified budget mapping, source-specific net-worth reconciliation, complete account valuation semantics, migration baseline and upgrade policy, reliable response to inserted workbook rows, stronger user-defined classification rules, exhaustive edge-case suite, full interactive charts, and verified Windows process smoke tests. Do not mark these complete before independently testing them.


## Running the test suite on a configured Windows dashboard

The pytest suite uses **synthetic files and ephemeral SQLite databases**. A developer or VPS may have a private `.env` containing `LIFE_DATA_SOURCE=onedrive` and a Graph cache under the app's shared instance folder; tests must **never** read those real caches or compete for active sync locks.

The relevant test fixtures explicitly set `LIFE_DATA_SOURCE=local` when reading generated mortgage/MFP files, and use a unique per-test `app.instance_path` for OneDrive sync/lock simulation. The Graph tests intentionally select `onedrive` but use `FakeClient` and a temporary instance directory; no remote auth/download is performed. MFP's in-process CSV cache is reset for each test fixture.

Do not "repair" a failing fixture by changing the application's production source-priority rules. `mortgage_tracking()` must still prefer the Graph cache when the live dashboard is in OneDrive mode.

In the current spending UI, year/month selectors are `#spending-year` and `#spending-month` (not removed legacy category selectors). The transaction explorer excludes internal transfers by default, and `include_transfers=true` opts in. Do not weaken assertions about amounts or categories to suppress a genuine regression.

~~~powershell
python -m pytest -q tests/test_finance_enhancements.py tests/test_graph_sync.py tests/test_mfp.py tests/test_spending_insights.py tests/test_app.py
python -m pytest -q
~~~

If a test unexpectedly returns **real** net-worth snapshots or MFP history, inspect its `LIFE_DATA_SOURCE`, `SOURCE_WORKBOOK`, `MFP_DATA_DIR` and `instance_path` before modifying application code. Never upload real finance/workout/weight data as test evidence.
