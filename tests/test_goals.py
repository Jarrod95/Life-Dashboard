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


def test_real_dashboard_sections():
    from app.goals import proximity
    wb = Workbook()
    ws = wb.active
    ws.title = "Dashboard!"
    ws["B3"] = "Last updated:"
    ws["D3"] = date(2026, 11, 20)
    ws["B11"] = "Ideal Body Shape"
    ws["B12"], ws["D12"], ws["E12"] = "Ratio", "Ideal", "Current"
    ws["B13"], ws["D13"], ws["E13"] = "Shoulder to Waist", 1.6, 1.51
    ws["B15"], ws["D15"], ws["E15"] = "Waist to Hip", "<0.9", .91
    ws["B27"], ws["D27"], ws["E27"] = "Muscle Goals", "Goal", "Current"
    ws["B28"], ws["D28"], ws["E28"] = "Chest", 110, 106.2
    rows, warnings = parse_ideals(wb)
    assert not warnings
    data = {k: v for _, k, v in rows}
    assert data["ratio_shouldertowaist"]["direction"] == "exact"
    assert data["ratio_waisttohip"]["direction"] == "decrease"
    assert data["shape_chest"]["target"] == 110
    assert data["shape_chest"]["current"] == 106.2
    assert proximity(120,150,"increase") == 80
    assert proximity(87.6,84,"decrease") == 95.9
    assert proximity(1.8,1.6,"exact") == 88.9


def test_unconfigured_observations_and_financial_targets(tmp_path):
    from app import create_app, db
    from app.body_composition import CompositionRow
    from app.models import NetWorthSnapshot
    from app.goals import report, save
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SOURCE_WORKBOOK": "", "LIFE_DATA_SOURCE": "local",
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path/"goals.sqlite")})
    with app.app_context():
        today = date.today()
        db.session.add(CompositionRow(source="manual", observed_on=today,
                       row_key="first", payload={"Weight":87.6}))
        db.session.add(NetWorthSnapshot(as_of_date=today, source_net_worth=-180000))
        db.session.commit()
        r = report()
        assert r["groups"]["composition"][0]["current"] == 87.6
        assert r["groups"]["finance"][0]["current"] == -180000
        save({"key":"net_worth","target":"-100000","direction":"increase"})
        assert report()["groups"]["finance"][0]["active"]["target"] == -100000
    assert app.test_client().get("/goals").status_code == 200
