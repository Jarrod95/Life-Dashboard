"""Local-administrator-only Graph connection and data-source settings."""
from flask import Blueprint, current_app, jsonify, render_template, request
from app.models import SyncRun
from app.integrations import graph_auth
from app.services.data_sources import SOURCES
from app.services.sync import sync_one, statuses

graph_pages = Blueprint("graph_pages", __name__)
graph_api = Blueprint("graph_api", __name__, url_prefix="/api/v1/data-sources")


@graph_pages.before_request
@graph_api.before_request
def local_admin_guard():
    # Single-user local application. Reverse proxy / public exposure is unsupported.
    if request.remote_addr not in ("127.0.0.1", "::1") and not current_app.config.get("TESTING"):
        return jsonify(error={"code": "forbidden", "message": "Local administrator only"}), 403
    if current_app.config.get("SECRET_KEY") == "local-development-only-change-me" and not current_app.config.get("TESTING"):
        return jsonify(error={"code": "unsafe_configuration", "message": "Set FLASK_SECRET_KEY first"}), 503


def json_error(exc, status=400):
    return jsonify(error={"code": getattr(exc, "code", "operation_failed"),
                          "message": str(exc)[:200]}), status


@graph_pages.get("/settings/data-sources")
def page():
    return render_template("data_sources.html", section="data-sources",
                           title="Data sources", sources=statuses(),
                           graph=graph_auth.status(),
                           provider=current_app.config.get("LIFE_DATA_SOURCE"))


@graph_api.get("")
def list_sources():
    return jsonify(data=statuses())


@graph_api.get("/graph/status")
def graph_status():
    return jsonify(data=graph_auth.status())


@graph_api.post("/graph/connect")
def connect():
    if current_app.config.get("LIFE_DATA_SOURCE") != "onedrive":
        return jsonify(error={"code": "not_configured", "message": "Enable LIFE_DATA_SOURCE=onedrive"}), 400
    try:
        return jsonify(data=graph_auth.begin_connect(current_app._get_current_object())), 202
    except graph_auth.GraphAuthError as exc:
        return json_error(exc)


@graph_api.post("/graph/disconnect")
def disconnect():
    try:
        graph_auth.disconnect()
        return jsonify(data={"status": "not_connected"})
    except graph_auth.GraphAuthError as exc:
        return json_error(exc)


@graph_api.post("/<source_key>/sync")
def sync_source(source_key):
    if source_key not in SOURCES:
        return jsonify(error={"code": "not_found", "message": "Unknown source"}), 404
    result = sync_one(source_key, force=(request.get_json(silent=True) or {}).get("force") is True)
    return jsonify(data=result), (503 if result["status"] == "failed" else 200)


@graph_api.get("/sync-runs")
def history():
    try:
        limit = min(100, max(1, int(request.args.get("limit", 25))))
    except ValueError:
        return jsonify(error={"code": "invalid_limit", "message": "Invalid limit"}), 400
    rows = SyncRun.query.order_by(SyncRun.id.desc()).limit(limit).all()
    return jsonify(data=[{"id": r.id, "source_key": r.source_key, "status": r.status,
                          "trigger": r.trigger, "started_at": r.started_at.isoformat() if r.started_at else None,
                          "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                          "bytes_downloaded": r.bytes_downloaded, "records_imported": r.records_imported,
                          "error_code": r.error_code, "error_summary": r.error_summary}
                         for r in rows])
