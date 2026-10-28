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
