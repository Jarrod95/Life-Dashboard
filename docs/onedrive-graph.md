# Personal OneDrive / Microsoft Graph ingestion

This is a **single-user, local-only** implementation. Do not expose the Flask
server publicly. The app uses delegated Microsoft personal-account permissions,
not application permissions or a client secret.

## Configuration

Install dependencies with `pip install -e ".[dev]"`. In the Azure app:
select "Personal Microsoft accounts", enable public client flows and grant
delegated `Files.Read` and `User.Read` permissions. The authority is
`https://login.microsoftonline.com/consumers`.

Set your already-prepared local `.env` values:

- `LIFE_DATA_SOURCE=onedrive`
- `MS_GRAPH_CLIENT_ID` to the public-client application ID
- `MS_GRAPH_SCOPES=User.Read Files.Read offline_access` (reserved MSAL scopes are filtered)
- `LIFE_FINANCE_ONEDRIVE_PATH` relative to the drive root
- `LIFE_BODY_COMPOSITION_ONEDRIVE_PATH` relative to the drive root
- `LIFE_GYMDAY_ONEDRIVE_DIR` to the GymDay ZIP folder
- `FLASK_SECRET_KEY` to a unique strong local value
- `LIFE_SYNC_INTERVAL_MINUTES=60`
- `LIFE_SYNC_ON_STARTUP=true`
- `LIFE_SYNC_LOCAL_FALLBACK=true` only if the local sources are trustworthy.

**Never commit .env, downloaded sources or the DPAPI token cache.** The
cache is stored at `instance/graph-msal-cache.dpapi` on Windows, encrypted
using Windows DPAPI under the user account running Flask. Non-Windows OSes
use an in-memory cache and must authenticate again after process restart.
An unattended token lifetime cannot be guaranteed.

## Initial setup and reconnect

1. Back up the existing SQLite file. Run `flask db upgrade`.
2. Restart Flask with the updated `.env`.
3. Open `http://127.0.0.1:5050/settings/data-sources`, click Connect,
   visit the Microsoft verification URL, enter the one-time code and consent.
   Alternatively run `flask graph-connect` in the same user environment.
4. Run `flask graph-test`: verifies /me, drive and three configured sources.
5. Run `flask sync-sources --all`, or sync individually from the UI.
6. If tokens expire, reconnect. Dashboard analytics remain cached in SQLite.

`flask sync-sources --source finance_workbook --force` reimports even when
the remote ETag has not changed. The service uses file locks per source,
metadata checks, SHA-256, importer versions and bounded Graph downloads.

## Scheduling and operations

With `LIFE_SYNC_ON_STARTUP=true`, a daemon thread starts non-blocking
periodic checks. This is suitable only for local single-process operation.
For a production process manager, use a single external scheduler:
Windows Task Scheduler can run `flask sync-sources --all` hourly with
`LIFE_SYNC_ON_STARTUP=false`. The file lock prevents duplicate imports,
but it is not a substitute for a central distributed scheduler.

`LIFE_DATA_SOURCE=local` retains existing imports and workbook paths.
A successful Graph import prevents older local files from overwriting it
during later remote outages. Remote mortgage reads use the managed
`instance/finance-graph-cache.xlsx` snapshot, not your original Windows
OneDrive path. Finance downloads and Graph content stay off ordinary pages.
The managed cache contains sensitive financial records; protect its directory.

## Offline tests

Run `python -m pytest -q`. These use synthetic fixtures and fake Graph
sessions, no real credentials or network. There is no GitHub Actions
dependency. The live connectivity check is deliberate and read-only:
`flask graph-test`.

## Limitations

- This is not a multi-user web application; local action routes reject
  non-loopback requests. A reverse proxy could defeat that assumption.
- No Graph upload, mutation, indefinite refresh guarantee, or general
  folder discovery browser is included.
- Graph permission failures can require consent or a new connection.
- The finance importer commits its upserts before the managed mortgage
  cache file replacement; file-system failure may require a forced retry.
- No unattended server authentication is available on a non-Windows host
  without additional approved token storage.
