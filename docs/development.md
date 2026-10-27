# Development and unfinished work

Install Python 3.12+ and `pip install -e '.[dev]'`. Run `python -m pytest -q` and `python -m ruff check .`, then `python run.py`.

The source Excel workbook was not uploaded into this execution environment. Run the dry-run import on Windows first; confirm year counts, snapshot dates, category classification and reported totals.

Outstanding relative to the supplied specification: verified budget mapping, source-specific net-worth reconciliation, complete account valuation semantics, migration baseline and upgrade policy, reliable response to inserted workbook rows, stronger user-defined classification rules, exhaustive edge-case suite, full interactive charts, and verified Windows process smoke tests. Do not mark these complete before independently testing them.
