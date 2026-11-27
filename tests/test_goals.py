from datetime import date, timedelta
from openpyxl import Workbook
from app.goals import completion, forecast, parse_ideals


def test_progress():
    assert completion(93.3, 88.3, 84, "decrease") == 53.8
    assert completion(100, 120, 140, "increase") == 50
    assert completion(100, 150, 140, "increase") == 100
    assert completion(100, 90, 140, "increase") == 0
    assert completion(None, 90, 140, "increase") is None


def test_forecast():
    today = date(2026, 11, 27)
    points = [(today-timedelta(days=7*i), 85+i*.4) for i in range(7,-1,-1)]
    assert forecast(points, 83, "decrease", "weight", today)["status"] == "estimated"
    assert forecast(points, 90, "increase", "weight", today)["status"] == "not_progressing"
    assert forecast(points[:1], 83, "decrease", "weight", today)["status"] == "stale"


def test_ideal_import():
    wb = Workbook()
    ws = wb.active
    ws.title = "Dashboard"
    ws.append(["Measurement", "Current", "Ideal"])
    ws.append(["Waist", 85, 80])
    ws.append(["Chest", 105, 115])
    result, warnings = parse_ideals(wb)
    assert not warnings
    assert {key: payload["target"] for _,key,payload in result} == {
        "shape_waist":80, "shape_chest":115}


def test_version_history(tmp_path):
    from app import create_app, db
    from app.body_composition import CompositionRow
    from app.goals import report, save

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path/"goals.sqlite")})
    with app.app_context():
        today = date.today()
        db.session.add(CompositionRow(source="manual", observed_on=today,
                       row_key="first", payload={"Weight":90}))
        db.session.commit()
        save({"key":"weight","target":"85","direction":"decrease","source":"manual"})
        g = report()["groups"]["composition"][0]["active"]
        assert g["completion"] == 0
        db.session.add(CompositionRow(source="manual", observed_on=today,
                       row_key="second", payload={"Weight":86}))
        db.session.commit()
        save({"key":"weight","target":"84","direction":"decrease","source":"manual",
              "version_id":str(g["id"]),"note":"revised"})
        r = report()
        assert len(r["history"]) == 1
        assert r["history"][0]["target"] == 85
        assert r["history"][0]["outcome"] == "revised"
        assert r["history"][0]["completion"] == 40
    assert app.test_client().get("/goals").status_code == 200
