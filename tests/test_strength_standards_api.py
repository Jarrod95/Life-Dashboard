"""Standards API integration tests with synthetic Gym Day and weight data only."""
from datetime import date

import pytest

from app import create_app, db
from app.body_composition import CompositionRow
from app.gymday import GymExercise, GymSession, GymSessionExercise, GymSet

SQUAT = "550e8400-e29b-41d4-a716-446655440000"
RDL = "550e8400-e29b-41d4-a716-446655440001"


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Never inherit a developer/VPS .env that points to OneDrive.
    # The test exercises the synthetic CSV stored under tmp_path only.
    from app import mfp
    monkeypatch.setattr(mfp, "_cache", {})
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
        "MFP_DATA_DIR": str(tmp_path), "LIFE_DATA_SOURCE": "local",
        "STRENGTH_MAPPING_PATH": str(mapping),
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
    assert data["bodyweight_method"] == "highest_90d"
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
    assert data["bodyweight"]["source"] == "manual"
    assert data["bodyweight"]["date"] == "2026-09-30"
    assert data["bodyweight"]["age_days"] == 3
    assert data["classification"]["label"] == "Excellent"
    assert data["classification"]["source_tier"] == "advanced_plus"
    assert data["benchmarks"]["good_kg"] == 90
    assert data["benchmarks"]["excellent_kg"] == 146.7
    assert data["benchmarks"]["elite_kg"] == 202.5
    assert data["next_milestone"]["gap_kg"] == 27.5


def test_per_session_weight_is_not_current_weight(app):
    result = app.test_client().get(endpoint("/exercises/" + SQUAT + "/progress")).json["data"]
    assert len(result) == 1
    row = result[0]
    assert row["bodyweight"]["weight_kg"] == 90
    assert row["bodyweight"]["date"] == "2026-09-30"
    assert row["relative_strength"] == 175 / 90
    assert row["classification"]["label"] == "Excellent"


def test_unmapped_exercise_ratio_only(app):
    item = app.test_client().get(endpoint("/summary?exercise_id=" + RDL)).json["data"]
    assert item["status"] == "unrated_exercise"
    assert item["classification"] is None
    assert item["benchmarks"] is None
    assert item["relative_strength"] == (160*(1+5/30))/90


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


def test_stale_current_weight_fails_closed(app, tmp_path):
    # Both sources now contain only measurements outside the trailing 90 days.
    (tmp_path / "myfitnesspal_weight_history.csv").write_text(
        "date,weight_kg\\n2026-04-01,90\\n".replace("\\n", "\n"))
    with app.app_context():
        CompositionRow.query.delete()
        db.session.commit()
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
    # Validate chart-specific rendering rather than banning legitimate table terminology.
    assert '<th scope="col">1RM (kg)</th>' in js
    bar_renderer = js.split("function plotBars(", 1)[1].split("function drawProgress(", 1)[0]
    assert 'label:"Load"' not in bar_renderer
    assert "axisTitle" not in bar_renderer and "legend" not in bar_renderer
    assert "ctx.fillText(b.label" in bar_renderer
    for name in ("--strength-bar-current", "--strength-bar-good",
                 "--strength-bar-excellent", "--strength-bar-elite"):
        assert name in js and name in css
    assert "life-theme-change" in js and "ResizeObserver" in js
    assert 'id="standard-sex"' in js
    assert 'id="standard-table-all"' in js
    assert 'params.set("window","90d")' in js
    assert "reloadCatalog()" in js
    assert "peak bodyweight from trailing 90 days" in js.lower()
    assert "Heaviest set" in js


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


def test_strength_fixture_uses_synthetic_local_mfp_even_when_env_is_onedrive(app, monkeypatch):
    from app.mfp import source_dir, load
    # The hosting user's LIFE_DATA_SOURCE may point at OneDrive; test config wins.
    monkeypatch.setenv("LIFE_DATA_SOURCE", "onedrive")
    with app.app_context():
        assert app.config["LIFE_DATA_SOURCE"] == "local"
        assert source_dir() == __import__("pathlib").Path(app.config["MFP_DATA_DIR"])
        assert [(r["date"], r["weight_kg"]) for r in load("weight")] == [
            ("2026-10-01", 88.0), ("2026-10-02", 87.0),
        ]


def test_exact_barbell_alias_populates_classification_targets_and_gap(app):
    bench = "550e8400-e29b-41d4-a716-446655440002"
    with app.app_context():
        db.session.add(GymExercise(id=bench, name="Barbell Bench Press",
                                   equipment="Barbell"))
        db.session.add(GymSessionExercise(id="se-bench", session_id="session-1",
                                        exercise_id=bench))
        db.session.flush()
        db.session.add(GymSet(id="bench-set", session_exercise_id="se-bench",
                              weight_kg=130, reps=6, complete=True, warmup=False))
        db.session.commit()
        client = app.test_client()
        selected = client.get(endpoint("/summary?exercise_id="+bench,
                                       "&sex=male")).json["data"]
        assert selected["status"] == "rated"
        assert selected["exercise"]["movement"] == "bench_press"
        assert selected["best_set"]["weight_kg"] == 130
        assert selected["best_set"]["one_rm_kg"] == 156
        assert selected["bodyweight"]["weight_kg"] == 90
        assert selected["classification"]["label"] in ("Good", "Excellent", "Elite")
        assert selected["benchmarks"]["good_kg"] > 0
        assert selected["benchmarks"]["elite_kg"] > selected["benchmarks"]["excellent_kg"]
        assert selected["relative_strength"] == 156/90
        all_rows = client.get(endpoint("/comparison?","&sex=male")).json["data"]
        bench_row = next(r for r in all_rows if r["exercise_id"] == bench)
        assert bench_row["classification"] == selected["classification"]["label"]
        assert bench_row["bodyweight_kg"] == 90
        assert bench_row["status"] == "rated"


def test_explicit_id_rejection_overrides_barbell_alias(app, tmp_path):
    p = tmp_path / "aliases.yaml"
    p.write_text("mappings:\n  " + SQUAT +
                 ":\n    approved: false\nname_mappings:\n"
                 "  Barbell Back Squat: back_squat\n")
    with app.app_context():
        app.config["STRENGTH_MAPPING_PATH"] = str(p)
        row = app.test_client().get(endpoint("/summary?exercise_id="+SQUAT,
                                             "&sex=male")).json["data"]
        assert row["status"] == "unrated_exercise"


def test_heaviest_eligible_set_wins_even_if_its_e1rm_is_lower(app):
    with app.app_context():
        db.session.add(GymSet(id="heavy-single", session_exercise_id="se-1",
                              weight_kg=165, reps=1, complete=True, warmup=False))
        db.session.commit()
        row = app.test_client().get(endpoint("/summary?exercise_id="+SQUAT)).json["data"]
        assert row["best_set"]["set_id"] == "heavy-single"
        assert row["best_set"]["weight_kg"] == 165
        assert row["best_set"]["one_rm_kg"] == 165


def test_default_90_day_window_excludes_older_heavier_load(app):
    with app.app_context():
        db.session.add(GymSession(id="session-old", name="Old leg day",
                                 local_date=date(2026, 3, 1), active=True))
        db.session.add(GymSessionExercise(id="se-old", session_id="session-old",
                                        exercise_id=SQUAT))
        db.session.flush()
        db.session.add(GymSet(id="very-heavy-old", session_exercise_id="se-old",
                              weight_kg=250, reps=1, complete=True, warmup=False))
        db.session.commit()
        client = app.test_client()
        recent = client.get(endpoint("/summary?exercise_id="+SQUAT)).json["data"]
        assert recent["period"]["window"] == "90d"
        assert recent["best_set"]["set_id"] == "set-1"
        all_time = client.get(endpoint("/summary?exercise_id="+SQUAT,
                                       "&window=all_time")).json["data"]
        assert all_time["best_set"]["set_id"] == "very-heavy-old"
        catalog = client.get(endpoint("/exercises")).json["data"]
        assert next(r for r in catalog if r["id"] == SQUAT)["eligible_sessions"] == 1


def test_summary_shows_bodyweight_without_any_valid_sets(app):
    wheel = "550e8400-e29b-41d4-a716-446655440006"
    with app.app_context():
        db.session.add(GymExercise(id=wheel, name="Ab Wheel Rollout", equipment=None))
        db.session.commit()
        row = app.test_client().get(endpoint("/summary?exercise_id="+wheel)).json["data"]
        assert row["status"] == "no_valid_sets"
        assert row["best_set"] is None
        assert row["bodyweight"]["weight_kg"] == 90
        assert row["classification"] is None


def test_benchmark_profile_must_be_valid(app):
    client = app.test_client()
    assert client.get(endpoint("/summary?exercise_id="+SQUAT,"&sex=unknown")).status_code == 400
    chosen = client.get(endpoint("/summary?exercise_id="+SQUAT,"&sex=female")).json["data"]
    assert chosen["status"] == "rated"
    assert chosen["benchmarks"]["good_kg"] != 90


def test_alias_name_does_not_map_unsupported_variants_or_wrong_equipment(app):
    squat_machine = "550e8400-e29b-41d4-a716-446655440007"
    rdl = "550e8400-e29b-41d4-a716-446655440008"
    with app.app_context():
        db.session.add_all([
            GymExercise(id=squat_machine, name="Barbell Squat", equipment="Smith Machine"),
            GymExercise(id=rdl, name="Barbell Romanian Deadlift", equipment="Barbell"),
        ])
        db.session.add_all([
            GymSessionExercise(id="se-machine", session_id="session-1",
                               exercise_id=squat_machine),
            GymSessionExercise(id="se-rdl", session_id="session-1",
                               exercise_id=rdl),
        ])
        db.session.flush()
        db.session.add_all([
            GymSet(id="set-machine", session_exercise_id="se-machine", weight_kg=250,
                   reps=3, complete=True, warmup=False),
            GymSet(id="set-rdl-new", session_exercise_id="se-rdl", weight_kg=180,
                   reps=6, complete=True, warmup=False),
        ])
        db.session.commit()
        client = app.test_client()
        for ident in (squat_machine, rdl):
            row = client.get(endpoint("/summary?exercise_id="+ident,
                                     "&sex=male")).json["data"]
            assert row["status"] == "unrated_exercise"
            assert row["relative_strength"] is not None
            assert row["classification"] is None
            assert row["benchmarks"] is None
            assert row["next_milestone"] is None
