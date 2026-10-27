import io
from datetime import date
from decimal import Decimal
import pytest
from openpyxl import Workbook
from app import create_app
from app.finance import mortgage_scenario
from app.importer import import_bytes, profile_bytes
from app.models import Transaction, NetWorthSnapshot, SourceRecord, ImportRun


@pytest.fixture
def app(tmp_path):
    application = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                              "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite")})
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def workbook_bytes():
    wb = Workbook()
    tx = wb.active
    tx.title = "Transactions_2026_NAB"
    tx.append(["Date", "Amount", "Account Number", "Transaction Type",
               "Transaction Details", "Category", "Merchant Name"])
    tx.append([date(2026, 2, 1), -10.25, "test", "purchase", "Coffee", "Food", "Cafe"])
    tx.append([date(2026, 2, 1), -10.25, "test", "purchase", "Coffee", "Food", "Cafe"])
    tx.append([date(2026, 2, 2), 100, "test", "transfer", "Transfer", "Transfers", "Internal"])
    nw = wb.create_sheet("Net Worth Tracking")
    nw["B1"] = date(2026, 1, 1)
    nw["B2"] = 1250.25
    nw["A12"] = "Cash"
    nw["B12"] = 500.0
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def test_empty_routes_and_validation(client):
    for url in ["/", "/finance", "/finance/net-worth", "/finance/spending",
                "/finance/budget", "/finance/mortgage", "/fitness", "/goals",
                "/health-dashboard", "/settings/imports", "/health"]:
        assert client.get(url).status_code == 200
    assert client.get("/api/v1/finance/transactions?page_size=201").status_code == 400
    assert client.get("/api/v1/finance/net-worth?from=bad").status_code == 400
    assert client.get("/api/v1/fitness/summary").json["status"] == "not_configured"


def test_import_idempotence_and_identical_distinct_purchases(app):
    with app.app_context():
        payload = workbook_bytes()
        profile = profile_bytes(payload)
        assert len(profile["transactions"]) == 3
        assert len(profile["snapshots"]) == 1
        first = import_bytes(payload, "fixture.xlsx")
        second = import_bytes(payload, "fixture.xlsx")
        assert first["status"] == "completed"
        assert second["counts"]["created"] == 0
        assert Transaction.query.count() == 3
        assert NetWorthSnapshot.query.first().source_net_worth == Decimal("1250.25")


def test_mortgage_offset_reduces_interest():
    baseline = mortgage_scenario(Decimal("100000"), Decimal("0.06"), Decimal(0),
                                  Decimal("1000"))
    with_offset = mortgage_scenario(Decimal("100000"), Decimal("0.06"),
                                    Decimal("20000"), Decimal("1000"))
    assert Decimal(with_offset["total_interest"]) < Decimal(baseline["total_interest"])
    assert with_offset["months"] <= baseline["months"]


def test_upload_validation(client):
    response = client.post("/api/v1/imports/finance/preview",
                           data={"file": (io.BytesIO(b"not excel"), "bad.csv")})
    assert response.status_code == 400


def test_solarized_source():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    css = (root / "app/static/css/solarized.css").read_text()
    assert "--solarized-base03:#002b36" in css
    assert "--solarized-base3:#fdf6e3" in css
    assert '[data-theme="dark"]' in css


def test_source_record_lineage_is_complete_and_reimport_updates_it(app):
    """Regression: SourceRecord NOT NULL fields must be set before ORM autoflush."""
    with app.app_context():
        original = workbook_bytes()
        result = import_bytes(original, "fixture.xlsx")
        records = SourceRecord.query.order_by(SourceRecord.row_number).all()
        assert len(records) == 3
        assert all(r.source_run_id == result["import_id"] for r in records)
        assert all(r.sheet == "Transactions_2026_NAB" for r in records)
        assert {r.row_number for r in records} == {2, 3, 4}
        assert all(r.payload["date"] and r.payload["amount"] for r in records)

        # Correcting an existing cell must update the source record, not duplicate it.
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(original))
        wb["Transactions_2026_NAB"]["B2"] = -12.75
        buffer = io.BytesIO()
        wb.save(buffer)
        revised = import_bytes(buffer.getvalue(), "fixture.xlsx")
        assert revised["counts"]["created"] == 0
        assert revised["counts"]["updated"] == 3
        assert Transaction.query.count() == 3
        assert SourceRecord.query.count() == 3
        assert ImportRun.query.count() == 2
        assert all(r.source_run_id == revised["import_id"] for r in SourceRecord.query.all())
        assert Transaction.query.filter_by(date=date(2026, 2, 1)).order_by(
            Transaction.id).first().signed_amount == Decimal("-12.75")
