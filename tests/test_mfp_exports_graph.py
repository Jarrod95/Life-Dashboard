"""Tests use synthetic MFP exports, never personal food or weight records."""
from app.services.mfp_exports import consolidate, discover, OUTPUTS
from app.integrations.onedrive import GraphError
import pytest


def test_merge_overlapping_csv_exports():
    older = b"date,calories,protein_g,food_entries\n2026-04-13,100,20,1\n"
    newer = b"date,calories,protein_g,food_entries\n2026-04-13,200,30,2\n"
    foods = b"date,meal,food,entry_id,calories\n2026-04-13,Lunch,A,99,200\n"
    meals = b"date,meal,calories\n2026-04-13,Lunch,200\n"
    weight = b"date,weight_kg\n2026-04-13,88.0\n"
    exports, counts = consolidate([
        ("daily", older), ("daily", newer), ("foods", foods),
        ("foods", foods), ("meals", meals), ("weight", weight)
    ])
    assert counts == {"daily": 1, "foods": 1, "meals": 1, "weight": 1}
    assert b"200,30,2" in exports[OUTPUTS["daily"]]


def test_incomplete_bundle_does_not_generate_partial_cache():
    with pytest.raises(ValueError, match="Missing MFP exports"):
        consolidate([("weight", b"date,weight_kg\n2026-04-13,88\n")])


def test_malformed_csv_rejected():
    with pytest.raises(ValueError):
        consolidate([("daily", b"date,calories,protein_g,food_entries\nnot-a-date,1,2,3\n")])


def test_discover_ignores_full_json_and_uses_csv(monkeypatch):
    monkeypatch.setattr("app.services.mfp_exports.source_path", lambda key: "Documents/mfp")
    class Client:
        def get_item_by_path(self, path):
            assert path == "Documents/mfp"
            return {"id": "folder", "folder": {}, "parentReference": {"driveId": "drive"}}
        def list_children(self, drive, folder):
            return [{"id": "1", "name": "mfp_2026_apr_oct_daily.csv", "file": {}, "eTag": "v1"},
                    {"id": "2", "name": "mfp_2026_apr_oct_full.json", "file": {}}]
    drive, items, fingerprint = discover(Client())
    assert drive == "drive"
    assert len(items) == 1 and items[0][1] == "daily"
    assert len(fingerprint) == 64
