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
        SOURCE_WORKBOOK=os.getenv("LIFE_FINANCE_XLSX_PATH", ""),
        GYMDAY_EXPORT_DIR=os.getenv("LIFE_GYMDAY_EXPORT_DIR", ""),
        APPLICATION_ROOT="/",
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    from app import models  # noqa: F401
    from app import gymday  # noqa: F401
    from app.routes import site, api
    app.register_blueprint(site)
    app.register_blueprint(api)
    app.register_blueprint(gymday.gym_pages)
    app.register_blueprint(gymday.gym_api)
    # Initial schema is created for clean local checkouts. Alembic revisions manage later changes.
    with app.app_context():
        db.create_all()
        if db.engine.dialect.name == "sqlite":
            with db.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        if os.getenv("LIFE_GYMDAY_IMPORT_ON_STARTUP", "false").lower() == "true" and not app.config.get("TESTING"):
            try:
                gymday.import_latest()
            except (OSError, ValueError, Exception):
                app.logger.exception("Gym Day startup import failed; existing dashboard remains available")
    @app.get("/health")
    def healthcheck():
        return jsonify(status="ok", application="Life-Dashboard"), 200
    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error={"code": "upload_too_large", "message": "File exceeds upload limit"}), 413
    return app
