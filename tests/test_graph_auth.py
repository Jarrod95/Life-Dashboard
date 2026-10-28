"""No live Microsoft sign-in is attempted in default tests."""
import pytest
from app.integrations import graph_auth


def test_reserved_scopes_removed(monkeypatch):
    monkeypatch.setenv("MS_GRAPH_SCOPES", "User.Read Files.Read offline_access openid profile")
    assert graph_auth.scopes() == ["User.Read", "Files.Read"]


def test_missing_permissions_fail(monkeypatch):
    monkeypatch.setenv("MS_GRAPH_SCOPES", "User.Read")
    with pytest.raises(graph_auth.GraphAuthError) as exc:
        graph_auth.scopes()
    assert exc.value.code == "invalid_scopes"


def test_no_client_id(monkeypatch):
    monkeypatch.delenv("MS_GRAPH_CLIENT_ID", raising=False)
    with pytest.raises(graph_auth.GraphAuthError) as exc:
        graph_auth.client()
    assert exc.value.code == "not_configured"


def test_local_endpoints_and_csrf(tmp_path, monkeypatch):
    from app import create_app
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": True,
                      "SECRET_KEY": "test-secret",
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "auth.sqlite")})
    client = app.test_client()
    assert client.get("/api/v1/data-sources").status_code == 200
    assert client.post("/api/v1/data-sources/graph/disconnect").status_code == 400
    assert client.get("/settings/data-sources").status_code == 200
    assert client.get("/api/v1/data-sources/sync-runs").status_code == 200


def test_source_selection_is_limited_to_connected_personal_drive(tmp_path, monkeypatch):
    from app import create_app
    from app.models import DataSourceState

    class FakeDrive:
        def drive(self):
            return {"id": "my-drive"}
        def get_item_by_id(self, drive, item):
            return {"id": item, "name": "Financial Dashboard.xlsx", "file": {},
                    "parentReference": {"driveId": "my-drive"}}

    monkeypatch.setattr("app.graph_routes.OneDriveClient", FakeDrive)
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SECRET_KEY": "test-only",
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "selection.sqlite")})
    test = app.test_client()
    wrong = test.post("/api/v1/data-sources/finance_workbook/select",
                      json={"drive_id": "other-drive", "item_id": "123"})
    assert wrong.status_code == 403
    success = test.post("/api/v1/data-sources/finance_workbook/select",
                        json={"drive_id": "my-drive", "item_id": "123"})
    assert success.status_code == 200
    with app.app_context():
        state = DataSourceState.query.filter_by(source_key="finance_workbook").one()
        assert state.selected_item_id == "123"


def test_nonlocal_graph_actions_blocked(tmp_path):
    from app import create_app
    app = create_app({"TESTING": False, "WTF_CSRF_ENABLED": False,
                      "SECRET_KEY": "test-only",
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "blocked.sqlite")})
    client = app.test_client()
    response = client.get("/api/v1/data-sources", environ_overrides={"REMOTE_ADDR": "10.0.0.1"})
    assert response.status_code == 403
