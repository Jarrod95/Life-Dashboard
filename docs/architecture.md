# Architecture

Flask `create_app` is defined in `app/__init__.py`; the SQLite models use Flask-SQLAlchemy, finance logic is in `app/finance.py`, openpyxl ingestion in `app/importer.py`, and same-origin pages and JSON endpoints in `app/routes.py`. Presentation uses server-rendered Jinja templates, standalone Solarized CSS, and vanilla JavaScript without Node or a remote CDN.

Pipeline: read-only source workbook → sheet profile and validation → transactional SQLite upserts → finance services → Jinja pages / API.

Transactions use source sheet + row for stable IDs; identical genuine purchases on distinct rows remain separate. Inserted or deleted rows can shift these IDs, so reimports after workbook reorganisation need manual review. Amounts use Decimal. Cross-sheet formula caches can be missing or stale.

The initial schema is bootstrapped with `db.create_all()`; Flask-Migrate is configured, but an Alembic baseline revision has not yet been shipped. Existing tables will not be automatically upgraded.
