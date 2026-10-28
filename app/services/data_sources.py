"""Graph source registry; paths are relative to the personal OneDrive root."""
import os
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


SOURCES = {
    "finance_workbook": ("LIFE_FINANCE_ONEDRIVE_PATH",
                         "Documents/Finance & Work/Tracking Spreadsheets/Financial Dashboard.xlsx"),
    "body_composition_workbook": ("LIFE_BODY_COMPOSITION_ONEDRIVE_PATH",
                                  "Documents/Fitness & Health/Body Composition.xlsx"),
    "gymday_latest_zip": ("LIFE_GYMDAY_ONEDRIVE_DIR",
                          "Documents/Codebases/sandbox-scripts/fitness_health/gymday/data"),
}
LIMITS = {"finance_workbook": 30_000_000, "body_composition_workbook": 30_000_000,
          "gymday_latest_zip": 90_000_000}


@dataclass(frozen=True)
class SourcePayload:
    content: bytes
    name: str
    drive_id: str
    item_id: str
    etag: str | None
    modified_at: str | None
    sha256: str


def source_path(key):
    if key not in SOURCES:
        raise ValueError("Unknown data source")
    setting, default = SOURCES[key]
    return os.getenv(setting, default)


def export_rank(item):
    name = item.get("name", "")
    match = re.search(r"daily_strength_(\d{4})_(\d{2})_(\d{2})", name, re.I)
    stamp = ""
    if match:
        try:
            stamp = datetime(*map(int, match.groups())).date().isoformat()
        except ValueError:
            pass
    return (stamp, item.get("lastModifiedDateTime") or "", name.casefold(), item.get("id", ""))


def resolve(client, key, saved=None):
    from app.integrations.onedrive import GraphError
    path = source_path(key)
    item = None
    selected = bool(saved and saved.selected_drive_id and saved.selected_item_id)
    if selected:
        item = client.get_item_by_id(saved.selected_drive_id, saved.selected_item_id)
    elif saved is not None and saved.drive_id and saved.item_id and key != "gymday_latest_zip":
        try:
            item = client.get_item_by_id(saved.drive_id, saved.item_id)
        except GraphError as exc:
            if exc.code != "not_found":
                raise
    if item is None:
        item = client.get_item_by_path(path)
    if key == "gymday_latest_zip":
        if "folder" not in item:
            raise GraphError("invalid_source", "GymDay source is not a folder")
        drive = item.get("parentReference", {}).get("driveId") or client.drive()["id"]
        candidates = [i for i in client.list_children(drive, item["id"])
                      if i.get("name", "").lower().endswith(".zip") and "file" in i]
        if not candidates:
            raise GraphError("not_found", "No GymDay export ZIP in configured folder")
        item = sorted(candidates, key=export_rank, reverse=True)[0]
    if "file" not in item:
        raise GraphError("invalid_source", "Configured source is not a file")
    if not item.get("name", "").lower().endswith(".zip" if key == "gymday_latest_zip" else ".xlsx"):
        raise GraphError("invalid_source", "Unexpected source extension")
    drive_id = item.get("parentReference", {}).get("driveId") or client.drive()["id"]
    return item, drive_id


def fetch_source(client, key, item, drive_id):
    content = client.download(drive_id, item["id"], max_bytes=LIMITS[key])
    return SourcePayload(content=content, name=item["name"], drive_id=drive_id,
                         item_id=item["id"], etag=item.get("eTag"),
                         modified_at=item.get("lastModifiedDateTime"),
                         sha256=sha256(content).hexdigest())
