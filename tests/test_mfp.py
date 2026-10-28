"""MyFitnessPal CSV integration tests using synthetic data only."""
from pathlib import Path
import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    data = tmp_path / "mfp"
    data.mkdir()
    (data / "myfitnesspal_weight_history.csv").write_text(
        "date,weight_kg\n2026-04-01,96\n2026-04-02,95.5\n2026-05-01,94\n", encoding="utf-8")
    (data / "mfp_2026_apr_oct_daily.csv").write_text(
        "date,calories,protein_g,carbs_g,fat_g,food_entries,goal_calories\n"
        "2026-04-01,2000,150,200,60,3,2400\n2026-04-02,0,0,0,0,0,2400\n", encoding="utf-8")
    (data / "mfp_2026_apr_oct_foods.csv").write_text(
        "date,meal,food,entry_id,calories,protein_g,carbs_g,fat_g\n"
        "2026-04-01,Breakfast,Oats,abc,350,20,40,8\n2026-04-01,Lunch,Chicken,def,500,50,10,18\n", encoding="utf-8")
    (data / "mfp_2026_apr_oct_meals.csv").write_text(
        "date,meal,calories,protein_g,carbs_g,fat_g\n"
        "2026-04-01,Breakfast,350,20,40,8\n2026-04-01,Lunch,500,50,10,18\n", encoding="utf-8")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite"),
                      "MFP_DATA_DIR": str(data), "GYMDAY_EXPORT_DIR": ""})
    return app.test_client()


def test_weight_metrics_and_date_filter(client):
    r = client.get("/api/v1/fitness/mfp/weight?year=2026&month=4")
    assert r.status_code == 200
    d = r.json["data"]
    assert d["summary"]["entries"] == 2
    assert d["summary"]["change_kg"] == -0.5
    assert d["summary"]["latest_kg"] == 95.5
    assert len(d["monthly"]) == 1
    assert client.get("/api/v1/fitness/mfp/weight?month=13").status_code == 400
    assert client.get("/fitness/weight").status_code == 200


def test_food_averages_exclude_missing_logging_days(client):
    r = client.get("/api/v1/fitness/mfp/food?year=2026&month=4")
    assert r.status_code == 200
    d = r.json["data"]
    assert d["summary"]["logged_days"] == 1
    assert d["summary"]["avg_calories"] == 2000
    assert d["summary"]["total_entries"] == 2
    assert len(d["entries"]) == 2
    assert client.get("/fitness/food-diary").status_code == 200


def test_search_meal_pagination_and_errors(client):
    r = client.get("/api/v1/fitness/mfp/food?meal=Breakfast&q=oats")
    assert r.status_code == 200
    assert r.json["meta"]["total"] == 1
    assert r.json["data"]["entries"][0]["food"] == "Oats"
    assert client.get("/api/v1/fitness/mfp/food?page_size=500").status_code == 400
    assert client.get("/api/v1/fitness/mfp/food?from=2026-05-02&to=2026-04-01").status_code == 400


def test_environment_nutrition_goals(client):
    app = client.application
    app.config.update(MFP_CALORIE_GOAL="1800", MFP_CARB_GOAL="73",
                      MFP_FAT_GOAL="60", MFP_PROTEIN_GOAL="203")
    goals = client.get("/api/v1/fitness/mfp/food").json["data"]["goals"]
    assert goals == {"calories": 1800.0, "carbs_g": 73.0,
                     "fat_g": 60.0, "protein_g": 203.0}
    app.config["MFP_PROTEIN_GOAL"] = "invalid"
    assert client.get("/api/v1/fitness/mfp/food").json["data"]["goals"]["protein_g"] == 203


def test_weight_projection_with_sufficient_recent_history():
    from app.mfp import weight_projection
    from datetime import date, timedelta
    start = date(2026, 8, 1)
    data = [{"date": (start+timedelta(days=i)).isoformat(), "weight_kg": 95-i*.07}
            for i in range(60)]
    projection = weight_projection(data)
    assert projection["days"] == 90
    assert len(projection["points"]) >= 14
    assert projection["points"][-1]["date"] == (start+timedelta(days=149)).isoformat()
    assert projection["points"][-1]["weight_kg"] < projection["points"][0]["weight_kg"]
    assert all(r["lower_kg"] <= r["weight_kg"] <= r["upper_kg"] for r in projection["points"])
    assert weight_projection(data[:5])["points"] == []
