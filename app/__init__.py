"""Local-first Flask application factory."""
import os
from pathlib import Path

from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def sqlite_foreign_keys(connection, _record):
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    root = Path(__file__).resolve().parent.parent
    from dotenv import load_dotenv
    load_dotenv(root / ".env", override=False)
    database = os.getenv("LIFE_DATABASE_PATH", "data/life-dashboard.sqlite")
    database_path = Path(database)
    if not database_path.is_absolute():
        database_path = root / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "local-development-only-change-me"),
        SQLALCHEMY_DATABASE_URI="sqlite:///" + str(database_path),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("LIFE_MAX_UPLOAD_MB", "20")) * 1024 * 1024,
        LIFE_DATA_SOURCE=os.getenv("LIFE_DATA_SOURCE", "local").lower(),
        LIFE_SYNC_LOCAL_FALLBACK=os.getenv("LIFE_SYNC_LOCAL_FALLBACK", "true").lower() == "true",
        GRAPH_FINANCE_CACHE_PATH=str(Path(app.instance_path) / "finance-graph-cache.xlsx"),
        SOURCE_WORKBOOK=os.getenv("LIFE_FINANCE_XLSX_PATH", ""),
        BODY_COMPOSITION_XLSX_PATH=os.getenv("LIFE_BODY_COMPOSITION_XLSX_PATH", ""),
        BODY_COMPOSITION_IMPORT_ON_STARTUP=os.getenv("LIFE_BODY_COMPOSITION_IMPORT_ON_STARTUP", "true").lower() == "true",
        BODY_WEIGHT_GOAL_KG=os.getenv("BODY_WEIGHT_GOAL_KG", "84"),
        BODY_FAT_GOAL_PCT=os.getenv("BODY_FAT_GOAL_PCT", "8"),
        GYMDAY_EXPORT_DIR=os.getenv("LIFE_GYMDAY_EXPORT_DIR", ""),
        MFP_DATA_DIR=os.getenv("LIFE_MFP_DATA_DIR") or None,
        **{key: os.getenv(key, default) for key, default in {
            "MFP_CALORIE_GOAL": "1800", "MFP_CARB_GOAL": "73",
            "MFP_FAT_GOAL": "60", "MFP_PROTEIN_GOAL": "203"}.items()},
        APPLICATION_ROOT="/",
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    from app import models  # noqa: F401
    from app import gymday  # noqa: F401
    from app import mfp  # noqa: F401
    from app import body_composition
    from app.routes import site, api
    from app.graph_routes import graph_pages, graph_api
    app.register_blueprint(site)
    app.register_blueprint(api)
    app.register_blueprint(graph_pages)
    app.register_blueprint(graph_api)
    app.register_blueprint(gymday.gym_pages)
    app.register_blueprint(gymday.gym_api)
    app.register_blueprint(mfp.mfp_pages)
    app.register_blueprint(mfp.mfp_api)
    app.register_blueprint(body_composition.pages)
    app.register_blueprint(body_composition.api)
    # Initial schema is created for clean local checkouts. Alembic revisions manage later changes.
    with app.app_context():
        db.create_all()
        if db.engine.dialect.name == "sqlite":
            with db.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        if app.config.get("LIFE_DATA_SOURCE") == "local" and app.config.get("BODY_COMPOSITION_IMPORT_ON_STARTUP") and not app.config.get("TESTING"):
            try:
                body_composition.import_source()
            except Exception:
                db.session.rollback()
                app.logger.exception("Body composition import failed; last successful snapshot retained")
        if app.config.get("LIFE_DATA_SOURCE") == "local" and os.getenv("LIFE_GYMDAY_IMPORT_ON_STARTUP", "false").lower() == "true" and not app.config.get("TESTING"):
            try:
                gymday.import_latest()
            except (OSError, ValueError, Exception):
                app.logger.exception("Gym Day startup import failed; existing dashboard remains available")
    from app.graph_cli import register_cli
    register_cli(app)
    # Non-blocking Graph polling runs only in the serving debug child or non-debug process.
    # A cross-process file lock in the sync service prevents duplicate imports.
    if (app.config.get("LIFE_DATA_SOURCE") == "onedrive"
            and not app.config.get("TESTING")
            and os.getenv("LIFE_SYNC_ON_STARTUP", "true").lower() == "true"
            and (not app.debug or os.getenv("WERKZEUG_RUN_MAIN") == "true")):
        from threading import Thread
        from time import sleep
        def poll_sources():
            from app.services.sync import sync_all
            sleep(3)
            while True:
                with app.app_context():
                    try:
                        sync_all(trigger="scheduled")
                    except Exception:
                        app.logger.warning("Scheduled Graph sync did not complete")
                interval = max(5, int(os.getenv("LIFE_SYNC_INTERVAL_MINUTES", "60")))
                sleep(interval * 60)
        Thread(target=poll_sources, name="graph-sync", daemon=True).start()
    @app.get("/health")
    def healthcheck():
        return jsonify(status="ok", application="Life-Dashboard"), 200
    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error={"code": "upload_too_large", "message": "File exceeds upload limit"}), 413
    return app
