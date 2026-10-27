# Private data and recovery

All personal workbook files, SQLite databases, logs, exports and backups must stay outside Git. They are excluded in `.gitignore`. No telemetry, credential collection or cloud publishing is part of this version. Flask binds only to `127.0.0.1`. Loopback binding does **not** replace authentication if the server is later made remotely accessible.

`scripts/Backup-Data.ps1` runs SQLite's backup API and retains ten timestamped snapshots by default. Backups are not encrypted; use BitLocker or encrypted storage.

Restore: stop the server, preserve the current DB and WAL files, copy a selected backup over the closed database, remove obsolete WAL/SHM files only while it is closed, start and validate `/health`. Test backups before relying on them.
