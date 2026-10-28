"""Offline contract tests: Graph authentication is always mocked."""
import pytest
from app.integrations.onedrive import OneDriveClient, GraphError, encode_path, ROOT


class Response:
    def __init__(self, code=200, payload=None, data=b"", headers=None):
        self.status_code, self.payload, self.data = code, payload or {}, data
        self.headers = headers or {}
        self.closed = False
    def json(self):
        return self.payload
    def close(self):
        self.closed = True
    def iter_content(self, chunk_size):
        yield self.data


class Session:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.replies.pop(0)


def test_encoded_segments():
    assert encode_path("Documents/Finance & Work/é% x.xlsx") == "Documents/Finance%20%26%20Work/%C3%A9%25%20x.xlsx"
    with pytest.raises(GraphError):
        encode_path("../secret.xlsx")


def test_me_drive_metadata_and_pagination():
    session = Session([Response(payload={"id": "user"}),
                       Response(payload={"id": "drive"}),
                       Response(payload={"id": "file", "file": {}}),
                       Response(payload={"value": [{"id": "1"}], "@odata.nextLink": ROOT + "/next"}),
                       Response(payload={"value": [{"id": "2"}]})])
    client = OneDriveClient(session, token_provider=lambda: "test")
    assert client.whoami()["id"] == "user"
    assert client.drive()["id"] == "drive"
    assert client.get_item_by_path("A & B/f.xlsx")["id"] == "file"
    assert [v["id"] for v in client.list_children("d", "f")] == ["1", "2"]
    assert "A%20%26%20B" in session.calls[2][0]


def test_no_auth_redirect_leak_and_stream_cap():
    session = Session([Response(302, headers={"Location": "https://download.example/test"}),
                       Response(data=b"zipdata")])
    client = OneDriveClient(session, token_provider=lambda: "sensitive-token")
    assert client.download("d", "i") == b"zipdata"
    assert "Authorization" not in session.calls[1][1].get("headers", {})
    session = Session([Response(data=b"123456789")])
    with pytest.raises(GraphError, match="size limit"):
        OneDriveClient(session, token_provider=lambda: "test").download("d", "i", max_bytes=2)


@pytest.mark.parametrize("code,expected", [(400,"bad_request"), (401,"reconnect_required"),
                                            (403,"forbidden"),(404,"not_found")])
def test_permanent_errors_not_retried(code, expected):
    session = Session([Response(code)])
    with pytest.raises(GraphError) as exc:
        OneDriveClient(session, token_provider=lambda: "test").whoami()
    assert exc.value.code == expected
    assert len(session.calls) == 1


def test_redirect_must_be_https():
    session = Session([Response(302, headers={"Location": "http://evil.example/"})])
    with pytest.raises(GraphError) as exc:
        OneDriveClient(session, token_provider=lambda: "test").download("d", "i")
    assert exc.value.code == "invalid_redirect"


def test_pagination_must_remain_graph_origin():
    session = Session([Response(payload={"value": [], "@odata.nextLink": "https://evil.example"})])
    with pytest.raises(GraphError):
        OneDriveClient(session, token_provider=lambda: "test").list_children("d", "i")


def test_throttling_exhaustion_and_retry_after(monkeypatch):
    from app.integrations import onedrive
    pauses = []
    monkeypatch.setattr(onedrive.time, "sleep", pauses.append)
    session = Session([Response(429, headers={"Retry-After": "1"}) for _ in range(4)])
    with pytest.raises(GraphError) as exc:
        OneDriveClient(session, token_provider=lambda: "test").drive()
    assert exc.value.code == "throttled"
    assert len(session.calls) == 4
    assert pauses == [1, 1, 1]


def test_transient_graph_error_recovers(monkeypatch):
    monkeypatch.setattr("app.integrations.onedrive.time.sleep", lambda _: None)
    session = Session([Response(503), Response(payload={"id": "ok"})])
    assert OneDriveClient(session, token_provider=lambda: "test").drive()["id"] == "ok"


def test_malformed_json_rejected():
    class BadResponse(Response):
        def json(self):
            raise ValueError("invalid json")
    with pytest.raises(GraphError) as exc:
        OneDriveClient(Session([BadResponse()]), token_provider=lambda: "test").drive()
    assert exc.value.code == "invalid_response"


def test_body_download_auth_header_is_present_only_for_graph():
    session = Session([Response(data=b"ok")])
    result = OneDriveClient(session, token_provider=lambda: "bearer").download("d", "i")
    assert result == b"ok"
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer bearer"
