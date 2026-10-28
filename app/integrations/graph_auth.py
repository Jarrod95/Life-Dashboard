"""Single-user delegated Microsoft authentication.

Windows DPAPI encrypts the persisted MSAL cache. On other platforms the token cache
is deliberately memory-only; no plaintext credentials are written to disk.
"""
import os
import threading
from pathlib import Path

import msal


RESERVED = {"openid", "profile", "offline_access"}
_lock = threading.RLock()
_cache = msal.SerializableTokenCache()
_client = None
_active_flow = None
_flow_state = "not_connected"
_flow_message = None


class GraphAuthError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def scopes():
    configured = os.getenv("MS_GRAPH_SCOPES", "User.Read Files.Read offline_access")
    values = list(dict.fromkeys(s for s in configured.split() if s.lower() not in RESERVED))
    if not {"User.Read", "Files.Read"}.issubset(set(values)):
        raise GraphAuthError("invalid_scopes", "Delegated User.Read and Files.Read scopes are required")
    return values


def cache_file():
    from flask import current_app
    return Path(current_app.instance_path) / "graph-msal-cache.dpapi"


def _load_cache():
    if os.name != "nt":
        return
    try:
        import win32crypt
        path = cache_file()
        if path.exists():
            _cache.deserialize(win32crypt.CryptUnprotectData(path.read_bytes(), None, None, None, 0)[1].decode())
    except (OSError, ValueError, ImportError) as exc:
        raise GraphAuthError("cache_unavailable", "Windows DPAPI token cache cannot be opened; reconnect") from exc


def _save_cache():
    if not _cache.has_state_changed or os.name != "nt":
        return
    try:
        import win32crypt
        file = cache_file()
        file.parent.mkdir(parents=True, exist_ok=True)
        encrypted = win32crypt.CryptProtectData(_cache.serialize().encode(), None, None, None, None, 0)
        tmp = file.with_suffix(".tmp")
        tmp.write_bytes(encrypted)
        os.replace(tmp, file)
    except (OSError, ImportError) as exc:
        raise GraphAuthError("cache_unavailable", "Secure Windows DPAPI cache could not be saved") from exc


def client():
    global _client
    with _lock:
        client_id = os.getenv("MS_GRAPH_CLIENT_ID", "").strip()
        if not client_id:
            raise GraphAuthError("not_configured", "MS_GRAPH_CLIENT_ID is required")
        authority = os.getenv("MS_GRAPH_AUTHORITY", "https://login.microsoftonline.com/consumers")
        if authority.rstrip("/") != "https://login.microsoftonline.com/consumers":
            raise GraphAuthError("unsupported_authority", "Personal OneDrive requires the consumers authority")
        if _client is None:
            _load_cache()
            _client = msal.PublicClientApplication(client_id, authority=authority, token_cache=_cache)
        return _client


def account():
    accounts = client().get_accounts()
    if len(accounts) > 1:
        raise GraphAuthError("multiple_accounts", "Disconnect before using a different Microsoft account")
    return accounts[0] if accounts else None


def access_token():
    with _lock:
        selected = account()
        if not selected:
            raise GraphAuthError("reconnect_required", "Connect your Microsoft account first")
        result = client().acquire_token_silent(scopes(), account=selected)
        _save_cache()
        if not result or "access_token" not in result:
            raise GraphAuthError("reconnect_required", "Microsoft session expired; reconnect")
        return result["access_token"]


def status():
    try:
        selected = account()
        if not selected:
            return {"status": "not_connected", "flow": _flow_state, "message": _flow_message}
        username = selected.get("username", "")
        masked = username[:2] + "***" if username else "Connected account"
        return {"status": "connected" if _flow_state != "reconnect_required" else "reconnect_required",
                "account": masked, "flow": _flow_state}
    except GraphAuthError as exc:
        return {"status": "reconnect_required", "code": exc.code, "message": str(exc)}


def begin_connect(app):
    global _active_flow, _flow_state, _flow_message
    with _lock:
        if _active_flow:
            raise GraphAuthError("already_connecting", "Connection is already in progress")
        flow = client().initiate_device_flow(scopes=scopes())
        if "user_code" not in flow:
            raise GraphAuthError("device_code_failed", "Microsoft did not provide a device code")
        _active_flow = flow
        _flow_state = "pending"
        _flow_message = None

    def complete():
        global _active_flow, _flow_state, _flow_message
        with app.app_context():
            try:
                result = client().acquire_token_by_device_flow(flow)
                with _lock:
                    if "access_token" in result:
                        if len(client().get_accounts()) != 1:
                            _cache.clear()
                            _flow_state, _flow_message = "reconnect_required", "Single-account binding failed"
                        else:
                            _save_cache()
                            _flow_state, _flow_message = "connected", None
                    else:
                        code = result.get("error", "authentication_failed")
                        _flow_state, _flow_message = "reconnect_required", str(code)[:100]
            except Exception:
                with _lock:
                    _flow_state, _flow_message = "reconnect_required", "Sign-in failed; retry connection"
            finally:
                with _lock:
                    _active_flow = None

    threading.Thread(target=complete, daemon=True, name="msal-device-flow").start()
    return {"status": "pending", "user_code": flow["user_code"],
            "verification_uri": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
            "expires_in": flow.get("expires_in", 900)}


def disconnect():
    global _client, _active_flow, _flow_state, _flow_message
    with _lock:
        if _active_flow:
            raise GraphAuthError("connect_pending", "Complete or cancel active sign-in first")
        _cache.clear()
        _client = None
        _flow_state, _flow_message = "not_connected", None
        if os.name == "nt":
            cache_file().unlink(missing_ok=True)
