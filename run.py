"""Start local Flask server after syncing the configured read-only workbook."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from app import create_app  # noqa: E402

app = create_app()


def sync_finances_on_startup(application=app):
    """Import changed source bytes exactly once per launch, with safe rollback on errors."""
    if application.config.get("LIFE_DATA_SOURCE") == "onedrive":
        logging.info("Graph mode: finance sync delegated to the Graph scheduler/service")
        return {"status": "scheduled_graph"}
    path = application.config.get("SOURCE_WORKBOOK", "").strip().strip('"')
    if not path:
        logging.info("No LIFE_FINANCE_XLSX_PATH configured; existing data retained")
        return {"status": "not_configured"}
    from app.importer import import_path
    with application.app_context():
        try:
            result = import_path(path)
            logging.info("Startup workbook sync: %s", result["status"])
            return result
        except (OSError, ValueError, Exception):
            # Import is atomic, and an inaccessible OneDrive file must not delete prior data.
            logging.exception("Startup workbook sync failed; retained existing database")
            return {"status": "failed"}


if __name__ == "__main__":
    sync_finances_on_startup()
    app.run(host="127.0.0.1", port=int(os.getenv("LIFE_PORT", "5050")), debug=False)
