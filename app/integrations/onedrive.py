"""Bounded, read-only Microsoft Graph client with safe download redirects."""
import random
import time
from urllib.parse import quote, urlparse

import requests

from .graph_auth import GraphAuthError, access_token

ROOT = "https://graph.microsoft.com/v1.0"
MAX_RETRIES = 3


class GraphError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def encode_path(value):
    parts = value.replace("\\", "/").strip("/").split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise GraphError("invalid_path", "OneDrive path must be drive-relative without traversal")
    return "/".join(quote(p, safe="") for p in parts)


class OneDriveClient:
    def __init__(self, session=None, token_provider=access_token):
        self.session = session or requests.Session()
        self.token_provider = token_provider

    def _request(self, url, *, stream=False):
        if not url.startswith(ROOT + "/"):
            raise GraphError("invalid_url", "Refusing untrusted Graph URL")
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self.session.get(url, headers={"Authorization": "Bearer " + self.token_provider()},
                                            timeout=(5, 30), stream=stream, allow_redirects=False)
            except requests.Timeout as exc:
                if attempt == MAX_RETRIES:
                    raise GraphError("unavailable", "Graph timed out") from exc
                time.sleep(min(2 ** attempt, 8))
                continue
            except requests.RequestException as exc:
                raise GraphError("unavailable", "Graph network failure") from exc
            if response.status_code in (429, 500, 502, 503, 504):
                response.close()
                if attempt == MAX_RETRIES:
                    raise GraphError("throttled" if response.status_code == 429 else "unavailable",
                                     "Graph retries exhausted")
                try:
                    delay = max(0, min(float(response.headers.get("Retry-After", 0)), 30))
                except ValueError:
                    delay = 0
                time.sleep(delay or min(2 ** attempt + random.random(), 8))
                continue
            errors = {400: "bad_request", 401: "reconnect_required", 403: "forbidden", 404: "not_found"}
            if response.status_code in errors:
                response.close()
                raise GraphError(errors[response.status_code], "Graph request rejected (HTTP %d)" % response.status_code)
            if response.status_code not in (200, 302):
                response.close()
                raise GraphError("unavailable", "Graph HTTP %d" % response.status_code)
            return response
        raise GraphError("unavailable", "Graph retries exhausted")

    def _json(self, url):
        response = self._request(url)
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("Expected object")
            return value
        except ValueError as exc:
            raise GraphError("invalid_response", "Malformed Graph JSON response") from exc
        finally:
            response.close()

    def whoami(self):
        return self._json(ROOT + "/me")

    def drive(self):
        return self._json(ROOT + "/me/drive")

    def root(self):
        return self._json(ROOT + "/me/drive/root")

    def get_item_by_path(self, drive_path):
        return self._json(ROOT + "/me/drive/root:/" + encode_path(drive_path))

    def get_item_by_id(self, drive_id, item_id):
        return self._json(ROOT + "/drives/" + quote(drive_id, safe="") +
                          "/items/" + quote(item_id, safe=""))

    def list_children(self, drive_id, item_id):
        url = (ROOT + "/drives/" + quote(drive_id, safe="") + "/items/" +
               quote(item_id, safe="") + "/children?$top=200")
        items = []
        for _ in range(30):
            page = self._json(url)
            items.extend(page.get("value", []))
            if len(items) > 5000:
                raise GraphError("too_many_items", "Folder exceeds listing limit")
            url = page.get("@odata.nextLink")
            if not url:
                return items
            if not url.startswith(ROOT + "/"):
                raise GraphError("invalid_url", "Unsafe Graph pagination link")
        raise GraphError("too_many_pages", "Pagination exceeded limit")

    def download(self, drive_id, item_id, *, max_bytes=25_000_000):
        url = (ROOT + "/drives/" + quote(drive_id, safe="") + "/items/" +
               quote(item_id, safe="") + "/content")
        response = self._request(url, stream=True)
        try:
            if response.status_code == 302:
                target = response.headers.get("Location", "")
                parsed = urlparse(target)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise GraphError("invalid_redirect", "Unsafe download URL")
                # Do not send bearer tokens to the redirected content host.
                response.close()
                try:
                    response = self.session.get(target, timeout=(5, 45), stream=True,
                                                allow_redirects=False)
                except requests.RequestException as exc:
                    raise GraphError("unavailable", "Download host unavailable") from exc
            if response.status_code != 200:
                raise GraphError("download_failed", "Download HTTP %d" % response.status_code)
            if int(response.headers.get("Content-Length", "0")) > max_bytes:
                raise GraphError("file_too_large", "Remote file exceeds download size limit")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > max_bytes:
                    raise GraphError("file_too_large", "Remote file exceeds download size limit")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            response.close()
