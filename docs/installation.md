# Installation and Graph integration troubleshooting

The `pyproject.toml` explicitly restricts setuptools discovery to the
`app` package and its subpackages. This matters because the repository
also has `data/`, `config/`, and `migrations/` at the root, none of which
should be included in the distributable Python package.

From **the repository root** in PowerShell, with the existing virtual
environment activated:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip show msal requests filelock
python -m pytest -q
flask db upgrade
```

If the original editable-install failure appeared first, the subsequent
`ModuleNotFoundError` errors for `requests`, `msal`, and `filelock`
are expected because installation stopped before dependency resolution.
Fix the packaging error first and then install; do not patch imports
or manually vend external packages.

**Your existing drive-relative paths are correct configuration syntax**,
and this fix does not change them:

```dotenv
LIFE_FINANCE_ONEDRIVE_PATH=Documents/Finance & Work/Tracking Spreadsheets/Financial Dashboard.xlsx
LIFE_BODY_COMPOSITION_ONEDRIVE_PATH=Documents/Fitness & Health/Body Composition.xlsx
LIFE_GYMDAY_ONEDRIVE_DIR=Documents/Codebases/sandbox-scripts/fitness_health/gymday/data
```

If Microsoft Graph reports a 404 after authentication, verify the actual
drive root with `flask graph-test` or the Data Sources browser. A Graph 404
is separate from setuptools packaging or missing Python dependencies.

For a clean install test in an isolated environment, run:

```powershell
python -m venv .venv-check
.\.venv-check\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv-check\Scripts\python.exe -m pip check
.\.venv-check\Scripts\python.exe -m pytest -q
```

Do not commit either virtual environment or local workbook files.
