"""Standards API integration tests with synthetic Gym Day and weight data only."""
from datetime import date

import pytest

from app import create_app, db
from app.body_composition import CompositionRow
from app.gymday import GymExercise, GymSession, GymSessionExercise, GymSet

SQUAT = "550e8400-e29b-41d4-a716-446655440000"
RDL = "550e8400-e29b-41d4-a716-446655440001"


@pytest.fixture
def app(tmp_path):
    mapping = tmp_path / "strength-exercise-mapping.yaml"
    mapping.write_text(
        "mappings:\n  " + SQUAT + ":\n"
        "    movement: back_squat\n"
        "    benchmark_provider: openprogression\n"
        "    load_convention: total_barbell_kg\n"
        "    approved: true\n")
    (tmp_path / "myfitnesspal_weight_history.csv").write_text(
        "date,weight_kg\n2026-10-01,88\n2026-10-02,87\n")
    app = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite"),
        "MFP_DATA_DIR": str(tmp_path), "STRENGTH_MAPPING_PATH": str(mapping),
        "STRENGTH_STANDARD_SEX": "male", "BODY_COMPOSITION_IMPORT_ON_STARTUP": False,
    })
    with app.app_context():
        db.session.add_all([
            GymExercise(id=SQUAT, name="Barbell Back Squat", equipment="Barbell"),
            GymExercise(id=RDL, name="Romanian deadlift", equipment="Barbell"),
            GymSession(id="session-1", name="Leg day", local_date=date(2026,10,1), active=True),
            GymSessionExercise(id="se-1", session_id="session-1", exercise_id=SQUAT),
            GymSessionExercise(id="se-2", session_id="session-1", exercise_id=RDL),
        ])
        db.session.flush()
        db.session.add_all([
            GymSet(id="set-1", session_exercise_id="se-1", weight_kg=150,
                   reps=5, complete=True, warmup=False),
            GymSet(id="warmup", session_exercise_id="se-1", weight_kg=250,
                   reps=5, complete=True, warmup=True),
            GymSet(id="incomplete", session_exercise_id="se-1", weight_kg=260,
                   reps=1, complete=False, warmup=False),
            GymSet(id="rdl-1", session_exercise_id="se-2", weight_kg=160,
                   reps=5, complete=True, warmup=False),
            CompositionRow(source="manual", observed_on=date(2026,9,30),
                           row_key="manual-1", payload={"Weight": 90}),
        ])
        db.session.commit()
        yield app
        db.session.remove()


def endpoint(path, extras=""):
    divider = "&" if "?" in path else "?"
    return "/api/v1/fitness/strength/standards" + path + divider + "as_of=2026-10-03" + extras


def test_page_routes_and_legacy_unchanged(app):
    client = app.test_client()
    html = client.get("/fitness/strength/standards")
    assert html.status_code == 200
    assert b"Strength Standards" in html.data
    assert b"strength-standards.js" in html.data
    assert client.get("/fitness/strength").status_code == 200
    assert client.get("/api/v1/fitness/strength/overview").status_code == 200


def test_metadata_and_movement_catalog(app):
    client = app.test_client()
    data = client.get(endpoint("/metadata")).json["data"]
    assert data["provider"] == "openprogression"
    assert data["provider_version"] == "1.0.0"
    assert data["license"].startswith("MIT")
    assert data["mapping_count"] == 1
    ids = {v["id"] for v in data["supported_movements"]}
    assert ids == {"back_squat","front_squat","overhead_squat",
                   "bench_press","strict_press","deadlift"}
    exercises = client.get(endpoint("/exercises")).json["data"]
    assert exercises[0]["id"] == SQUAT and exercises[0]["rated"]
    assert exercises[1]["id"] == RDL and not exercises[1]["rated"]


def test_summary_bodyweight_and_milestones(app):
    data = app.test_client().get(endpoint("/summary?exercise_id=" + SQUAT)).json["data"]
    assert data["status"] == "rated"
    assert data["best_set"]["one_rm_kg"] == 175
    assert data["best_set"]["one_rm_kind"] == "estimated"
    assert data["best_set"]["set_id"] == "set-1"
    assert data["bodyweight"]["source"] == "mfp"
    assert data["bodyweight"]["date"] == "2026-10-02"
    assert data["bodyweight"]["age_days"] == 1
    assert data["classification"]["label"] == "Excellent"
    assert data["classification"]["source_tier"] == "advanced_plus"
    assert data["benchmarks"]["good_kg"] == 87
    assert data["benchmarks"]["excellent_kg"] == 141.81
    assert data["benchmarks"]["elite_kg"] == 195.75
    assert data["next_milestone"]["gap_kg"] == 20.75


def test_per_session_weight_is_not_current_weight(app):
    result = app.test_client().get(endpoint("/exercises/" + SQUAT + "/progress")).json["data"]
    assert len(result) == 1
    row = result[0]
    assert row["bodyweight"]["weight_kg"] == 88
    assert row["bodyweight"]["date"] == row["date"]
    assert row["relative_strength"] == 175 / 88
    assert row["classification"]["label"] == "Excellent"


def test_unmapped_exercise_ratio_only(app):
    item = app.test_client().get(endpoint("/summary?exercise_id=" + RDL)).json["data"]
    assert item["status"] == "unrated_exercise"
    assert item["classification"] is None
    assert item["benchmarks"] is None
    assert item["relative_strength"] == (160*(1+5/30))/87


def test_comparison_csv_and_safe_spreadsheet_values(app):
    client = app.test_client()
    all_rows = client.get(endpoint("/comparison")).json
    assert all_rows["meta"]["total"] == 2
    assert all_rows["data"][0]["rated"]
    assert not all_rows["data"][1]["rated"]
    csv_response = client.get(endpoint("/comparison.csv"))
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["Content-Type"]
    assert "openprogression" in csv_response.get_data(as_text=True)
    with app.app_context():
        db.session.get(GymExercise, RDL).name = '=HYPERLINK("https://invalid")'
        db.session.commit()
    content = client.get(endpoint("/comparison.csv")).get_data(as_text=True)
    assert "'=HYPERLINK" in content


def test_unapproved_mapping_is_never_rated(app, tmp_path):
    with app.app_context():
        p = tmp_path / "unapproved.yaml"
        p.write_text("mappings:\n  " + SQUAT +
                     ":\n    movement: back_squat\n    approved: false\n")
        app.config["STRENGTH_MAPPING_PATH"] = str(p)
        row = app.test_client().get(endpoint("/summary?exercise_id=" + SQUAT)).json["data"]
        assert row["status"] == "unrated_exercise"
        assert row["classification"] is None


def test_missing_sex_is_configuration_required(app):
    with app.app_context():
        app.config["STRENGTH_STANDARD_SEX"] = ""
        row = app.test_client().get(endpoint("/summary?exercise_id=" + SQUAT)).json["data"]
        assert row["status"] == "configuration_required"
        assert row["classification"] is None


def test_manual_weight_fallback_when_mfp_missing(app, tmp_path):
    (tmp_path / "myfitnesspal_weight_history.csv").unlink()
    row = app.test_client().get(endpoint("/summary?exercise_id=" + SQUAT)).json["data"]
    assert row["bodyweight"]["source"] == "manual"
    assert row["bodyweight"]["weight_kg"] == 90


def test_stale_current_weight_fails_closed(app):
    row = app.test_client().get(
        "/api/v1/fitness/strength/standards/summary?exercise_id="+SQUAT+
        "&as_of=2026-11-05&window=all_time").json["data"]
    assert row["status"] == "stale_bodyweight"
    assert row["classification"] is None
    assert row["relative_strength"] is None


def test_all_time_contextual_not_recent_record(app):
    item = app.test_client().get(endpoint("/summary?exercise_id="+SQUAT,"&window=all_time")).json["data"]
    assert item["status"] == "rated"
    assert "contextual" in item["reason"]


def test_date_intersection_and_validation(app):
    client = app.test_client()
    sept = client.get(endpoint("/summary?exercise_id="+SQUAT,"&year=2026&month=9")).json["data"]
    assert sept["status"] == "no_valid_sets"
    octo = client.get(endpoint("/summary?exercise_id="+SQUAT,"&year=2026&month=10")).json["data"]
    assert octo["status"] == "rated"
    assert client.get(endpoint("/summary?exercise_id="+SQUAT,"&window=bad")).status_code == 400
    assert client.get(endpoint("/summary?exercise_id="+SQUAT,"&from=2026-12-01&to=2026-01-01")).status_code == 400
    assert client.get("/api/v1/fitness/strength/standards/summary?exercise_id="+SQUAT+"&as_of=nope").status_code == 400
    assert client.get("/api/v1/fitness/strength/standards/summary?exercise_id="+SQUAT+"&as_of=3000-01-01").status_code == 400
    assert client.get(endpoint("/summary?exercise_id=not-found")).status_code == 404
    assert client.get(endpoint("/summary")).status_code == 400
    assert client.get(endpoint("/comparison?","&page_size=201")).status_code == 400


def test_source_unavailable_produces_no_rating(app):
    with app.app_context():
        app.config["STRENGTH_BENCHMARK_PATH"] = "/nonexistent/benchmarks.json"
        client = app.test_client()
        item = client.get(endpoint("/summary?exercise_id="+SQUAT)).json["data"]
        assert item["status"] == "benchmark_unavailable"
        assert item["classification"] is None
        assert client.get(endpoint("/metadata")).json["data"]["source_error"]


def test_ui_static_contract(app):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    js = (root/"app/static/js/strength-standards.js").read_text()
    css = (root/"app/static/css/strength.css").read_text()
    assert "Your 1RM" in js and '"Good"' in js and '"Excellent"' in js and '"Elite"' in js
    assert "Load</" not in js and 'label:"Load"' not in js and "axisTitle" not in js
    for name in ("--strength-bar-current", "--strength-bar-good",
                 "--strength-bar-excellent", "--strength-bar-elite"):
        assert name in js and name in css
    assert "life-theme-change" in js and "ResizeObserver" in js


def test_session_best_and_period_tie_break_without_duplicated_points(app):
    with app.app_context():
        db.session.add_all([
            GymSession(id="session-2", local_date=date(2026,10,2),
                       name="Leg day 2", active=True),
            GymSessionExercise(id="se-3", session_id="session-2",exercise_id=SQUAT),
        ])
        db.session.flush()
        db.session.add_all([
            GymSet(id="set-4", session_exercise_id="se-3",
                   weight_kg=150,reps=5,complete=True,warmup=False),
            GymSet(id="set-5", session_exercise_id="se-3",
                   weight_kg=100,reps=5,complete=True,warmup=False),
        ])
        db.session.commit()
        client=app.test_client()
        series=client.get(endpoint("/exercises/"+SQUAT+"/progress")).json["data"]
        assert len(series)==2
        assert [x["one_rm_kg"] for x in series] == [175,175]
        summary=client.get(endpoint("/summary?exercise_id="+SQUAT)).json["data"]
        assert summary["best_set"]["session_id"] == "session-2"
        assert summary["best_set"]["set_id"] == "set-4"
        assert summary["best_set"]["date"] == "2026-10-02"
