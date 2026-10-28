"""Read MyFitnessPal CSV bundles from OneDrive into a managed VPS cache."""
import csv
import hashlib
import io
import re
from datetime import date
from pathlib import Path

from app.integrations.onedrive import GraphError
from app.services.data_sources import source_path

OUTPUTS = {"daily": "mfp_2026_apr_oct_daily.csv", "foods": "mfp_2026_apr_oct_foods.csv", "meals": "mfp_2026_apr_oct_meals.csv", "weight": "myfitnesspal_weight_history.csv"}
REQUIRED = {"daily": {"date", "calories", "protein_g", "food_entries"}, "foods": {"date", "meal", "food", "calories"}, "meals": {"date", "meal", "calories"}, "weight": {"date", "weight_kg"}}
PATTERN = re.compile(r"^mfp_.*_(daily|foods|meals)\.csv$", re.I)


def discover(client, state=None):
    if state is not None and state.selected_drive_id and state.selected_item_id:
        folder = client.get_item_by_id(state.selected_drive_id, state.selected_item_id)
    else:
        folder = client.get_item_by_path(source_path("mfp_exports"))
    if "folder" not in folder:
        raise GraphError("invalid_source", "MFP source must be a folder")
    drive = folder.get("parentReference", {}).get("driveId") or client.drive()["id"]
    items = []
    for item in client.list_children(drive, folder["id"]):
        name = item.get("name", "")
        match = PATTERN.fullmatch(name)
        if "file" in item and (match or name.lower() == OUTPUTS["weight"]):
            items.append((item, match.group(1).lower() if match else "weight"))
    if not items:
        raise GraphError("not_found", "No MFP CSV exports found")
    items.sort(key=lambda x: (x[0].get("lastModifiedDateTime", ""), x[0]["name"]))
    fingerprint = hashlib.sha256(repr([(i["id"], i.get("eTag")) for i, _ in items]).encode()).hexdigest()
    return drive, items, fingerprint


def consolidate(files):
    grouped = {key: {} for key in OUTPUTS}
    columns = {}
    for kind, content in files:
        if len(content) > 50_000_000:
            raise ValueError("MFP file exceeds limit")
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if not REQUIRED[kind].issubset(reader.fieldnames or []):
                raise ValueError("Invalid MFP " + kind + " columns")
            columns[kind] = reader.fieldnames
            for index, row in enumerate(reader):
                date.fromisoformat(row["date"])
                if kind == "foods":
                    key = row.get("entry_id") or (row["date"], row.get("meal"), row.get("food"), index)
                elif kind == "meals":
                    key = (row["date"], row["meal"])
                else:
                    key = row["date"]
                grouped[kind][key] = row
        except (UnicodeError, csv.Error) as exc:
            raise ValueError("Invalid MFP CSV") from exc
    missing = set(OUTPUTS) - set(columns)
    if missing:
        raise ValueError("Missing MFP exports: " + ", ".join(sorted(missing)))
    results = {}
    for kind, output in OUTPUTS.items():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns[kind], extrasaction="ignore")
        writer.writeheader()
        for key in sorted(grouped[kind], key=str):
            writer.writerow(grouped[kind][key])
        results[output] = buffer.getvalue().encode("utf-8-sig")
    return results, {key: len(value) for key, value in grouped.items()}
