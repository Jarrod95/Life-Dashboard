"""Synthetic Gym Day regression tests: never require private workout exports."""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app import create_app, db
from app.gymday import (GymSession, GymSet, archive_candidates, e1rm, import_latest,
                        set_volume, timestamp)


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite"),
                      "GYMDAY_EXPORT_DIR": str(tmp_path), "WTF_CSRF_ENABLED": False})
    with app.app_context():
        yield app
        db.session.remove()


def fixture_zip(folder, name="daily_strength_2026_10_21.zip"):
    start = int(datetime(2026, 10, 20, 7, 0, tzinfo=timezone.utc).timestamp()*1000)
    payload = {
        "Exercise.json": [{"id": "exercise-1", "name": "Bench press",
                           "primaryMuscleGroups": [{"name": "Chest"}],
                           "secondaryMuscleGroups": [{"name": "Triceps"}]}],
        "WorkoutSession.json": [{"id": "session-1", "name": "Push", "startDate": start,
          "endDate": start+3_600_000, "workoutSessionExercises": [
              {"id": "session-exercise-1", "position": 0,
               "exercise": {"id": "exercise-1", "name": "Bench press",
                            "primaryMuscleGroups": [{"name": "Chest"}]},
               "workoutSessionSets": [
                   {"id": "set-1", "set": 1, "weight": 100, "measurementUnit": "kg",
                    "reps": 5, "isComplete": True, "warmUp": False},
                   {"id": "set-2", "set": 2, "weight": 40, "measurementUnit": "kg",
                    "reps": 10, "isComplete": True, "warmUp": True},
                   {"id": "set-3", "set": 3, "weight": 110, "measurementUnit": "kg",
                    "reps": 3, "isComplete": False, "warmUp": False}]}]}],
        "WorkoutSessionExercise.json": [{"id": "session-exercise-1"}],
        "WorkoutSessionSet.json": [{"id": "set-1"}, {"id": "set-2"}, {"id": "set-3"}]}
    path = folder / name
    with zipfile.ZipFile(path, "w") as z:
        for member, value in payload.items():
            z.writestr(member, json.dumps(value))
    return path


def test_discovery_orders_by_embedded_date(tmp_path):
    fixture_zip(tmp_path, "daily_strength_2026_10_21.zip")
    fixture_zip(tmp_path, "daily_strength_2026_10_24(1).zip")
    assert archive_candidates(tmp_path)[0].name == "daily_strength_2026_10_24(1).zip"


def test_epoch_milliseconds_and_timezone():
    assert timestamp(1672640495622).year == 2023
    assert timestamp(None) is None


def test_import_idempotent_and_metrics(app, tmp_path):
    fixture_zip(tmp_path)
    with app.app_context():
        first = import_latest()
        assert first["status"] == "success"
        assert GymSession.query.count() == 1
        assert GymSet.query.count() == 3
        assert import_latest()["status"] == "unchanged"
        assert GymSet.query.count() == 3
        s = db.session.get(GymSet, "set-1")
        assert round(e1rm(s), 4) == round(100 * (1+5/30), 4)
        assert set_volume(s) == 500
        assert set_volume(db.session.get(GymSet, "set-2")) == 0
        assert set_volume(db.session.get(GymSet, "set-3")) == 0
        client = app.test_client()
        overview = client.get("/api/v1/fitness/strength/overview?year=2026&month=10")
        assert overview.status_code == 200
        kpis = overview.json["data"]["kpis"]
        assert kpis["sessions"] == 1
        assert kpis["working_sets"] == 1
        assert kpis["volume_kg"] == 500
        assert kpis["reps"] == 5
        assert client.get("/api/v1/fitness/strength/overview?month=99").status_code == 400
        assert client.get("/fitness/strength").status_code == 200


def test_bad_zip_preserves_good_state(app, tmp_path):
    fixture_zip(tmp_path)
    with app.app_context():
        import_latest()
        (tmp_path / "daily_strength_2026_10_30.zip").write_bytes(b"bad zip")
        result = import_latest()
        assert result["status"] == "unchanged"
        assert result["warnings"]
        assert GymSession.query.count() == 1


def test_missing_configuration(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "bare.sqlite"),
                      "GYMDAY_EXPORT_DIR": ""})
    with app.app_context(), pytest.raises(ValueError, match="Configure"):
        import_latest()


def test_startup_import_from_dotenv(tmp_path, monkeypatch):
    fixture_zip(tmp_path)
    # App factory accepts configuration overrides, and startup import is opt-in by
    # directory configuration. No manual CLI invocation should be necessary.
    monkeypatch.setenv("LIFE_GYMDAY_IMPORT_ON_STARTUP", "true")
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "startup.sqlite"),
                      "GYMDAY_EXPORT_DIR": str(tmp_path)})
    with app.app_context():
        assert GymSession.query.count() == 1
        from app.gymday import GymImport
        assert GymImport.query.filter_by(status="success").count() == 1
    monkeypatch.delenv("LIFE_GYMDAY_IMPORT_ON_STARTUP", raising=False)


def test_real_export_unit_classes_are_not_tonnage(tmp_path):
    from app.gymday import kg
    assert kg(50, "kg") == 50
    assert kg(10, "km") is None
    assert kg(10, None) is None


def test_month_calendar_returns_each_day_and_session_tonnage(app, tmp_path):
    fixture_zip(tmp_path)
    with app.app_context():
        import_latest()
        client = app.test_client()
        response = client.get("/api/v1/fitness/strength/calendar?year=2026&month=10")
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["year"] == 2026
        assert payload["month"] == 10
        # 20 October UTC morning stays the same Sydney-local date.
        assert payload["days"] == [{
            "date": "2026-10-20", "total_volume_kg": 500.0,
            "sessions": [{"id": "session-1", "name": "Push", "volume_kg": 500.0}]
        }]
        assert client.get("/api/v1/fitness/strength/calendar?year=2026&month=11").json["data"]["days"] == []
        for query in ("year=2026&month=13", "year=2026", "year=x&month=10"):
            assert client.get("/api/v1/fitness/strength/calendar?" + query).status_code == 400
