import io
from datetime import date
from decimal import Decimal
import pytest
from openpyxl import Workbook
from app import create_app
from app.finance import mortgage_scenario
from app.importer import import_bytes, profile_bytes
from app.models import Transaction, NetWorthSnapshot, SourceRecord, ImportRun, AccountValuation


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


def test_valuation_insert_and_corrected_snapshot_upsert(app):
    """Regression: complete NOT NULL valuation fields before database flush."""
    with app.app_context():
        original = workbook_bytes()
        first = import_bytes(original, "fixture.xlsx")
        valuations = AccountValuation.query.all()
        assert first["status"] == "completed"
        assert len(valuations) == 1
        assert valuations[0].amount_aud == Decimal("500.00")
        assert valuations[0].kind == "asset"
        assert valuations[0].category == "cash"
        assert valuations[0].source_reference
        snapshot_id = valuations[0].snapshot_id
        valuation_id = valuations[0].id

        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(original))
        wb["Net Worth Tracking"]["B12"] = 725.50
        buf = io.BytesIO()
        wb.save(buf)
        result = import_bytes(buf.getvalue(), "fixture.xlsx")
        assert result["status"] == "completed"
        assert AccountValuation.query.count() == 1
        updated = AccountValuation.query.one()
        assert updated.id == valuation_id
        assert updated.snapshot_id == snapshot_id
        assert updated.amount_aud == Decimal("725.50")


def test_category_spending_api_filters_year_and_month_and_excludes_transfers(app):
    from app.models import Category
    from app import db
    with app.app_context():
        import_bytes(workbook_bytes(), "fixture.xlsx")
        food = Category.query.filter_by(name="Food").one()
        client = app.test_client()
        all_data = client.get("/api/v1/finance/spending/categories").json["data"]
        assert all_data == [{"category": "Food", "spending": "20.50"}]
        feb = client.get("/api/v1/finance/spending/categories"
                         "?from=2026-02-01&to=2026-02-28")
        assert feb.status_code == 200
        assert feb.json["data"] == all_data
        jan = client.get("/api/v1/finance/spending/categories"
                         "?from=2026-01-01&to=2026-01-31")
        assert jan.json["data"] == []
        assert client.get("/api/v1/finance/spending/categories?from=invalid").status_code == 400
        assert client.get("/api/v1/finance/spending/years").json["data"] == [2026]
        # Refunds reduce net category spending in their original category.
        db.session.add(Transaction(
            source_key="fixture-refund", date=date(2026, 2, 3),
            signed_amount=Decimal("5.25"), category_id=food.id,
            raw_description="Refund", excluded_from_spending=False,
            income_flag=False, transfer_flag=False))
        db.session.commit()
        after = client.get("/api/v1/finance/spending/categories"
                           "?from=2026-02-01&to=2026-02-28").json["data"]
        assert after == [{"category": "Food", "spending": "15.25"}]


def test_chart_ui_mountpoints(client):
    page = client.get("/finance/spending").get_data(as_text=True)
    assert 'id="category-year"' in page
    assert 'id="category-month"' in page
    assert 'id="category-chart"' in page
    assert 'id="spending-chart"' in page
    assert 'js/charts.js' in page
    networth = client.get("/finance/net-worth").get_data(as_text=True)
    assert 'id="networth-chart"' in networth
    assert 'id="networth-tooltip"' in networth


def test_westpac_multi_account_and_income_import(app):
    from app.importer import transaction_rows
    from openpyxl import Workbook
    from app.models import Account
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Transactions_Westpac_All!"
    sheet.append(["Transaction Date", "Amount", "Account Name",
                  "Transaction Description", "Category"])
    sheet.append([date(2026, 1, 12), 3200.10, "Savings", "Salary payroll from employer", ""])
    sheet.append([date(2026, 1, 13), -45.25, "Spending", "Groceries", "Food"])
    sheet.append([date(2026, 1, 14), -100.00, "Savings", "Internal transfer", "Transfer"])
    sheet.append([date(2026, 1, 13), -45.25, "Spending", "Groceries", "Food"])
    stream = io.BytesIO()
    wb.save(stream)
    with app.app_context():
        rows, warnings = transaction_rows(wb)
        assert not warnings
        assert len(rows) == 4
        assert rows[0]["account"] == "Savings"
        imported = import_bytes(stream.getvalue(), "fixture.xlsx")
        assert imported["status"] == "completed"
        assert Transaction.query.count() == 4
        assert Account.query.filter_by(display_name="Westpac: Savings").one()
        assert Account.query.filter_by(display_name="Westpac: Spending").one()
        assert Transaction.query.filter_by(income_flag=True).count() == 1
        assert Transaction.query.filter_by(excluded_from_spending=True).count() == 1
        assert import_bytes(stream.getvalue(), "fixture.xlsx")["status"] == "unchanged"
        assert Transaction.query.count() == 4


def test_westpac_debit_credit_headers(app):
    from openpyxl import Workbook
    from app.importer import transaction_rows
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions_Westpac_All!"
    ws.append(["Date", "Description", "Account", "Debit", "Credit"])
    ws.append([date(2026, 3, 1), "Groceries", "Everyday", 22.75, None])
    ws.append([date(2026, 3, 2), "Salary", "Everyday", None, 1000])
    rows, warnings = transaction_rows(wb)
    assert not warnings
    assert [r["amount"] for r in rows] == [Decimal("-22.75"), Decimal("1000.00")]


def test_startup_module_declares_explicit_import_and_preserves_old_data():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "run.py").read_text()
    assert "load_dotenv(ROOT / \".env\")" in source
    assert "sync_finances_on_startup()" in source
    assert "import_path(path)" in source


def test_real_westpac_header_layout_with_separate_amounts(app):
    """Matches uploaded Westpac layout, with fabricated, non-private account rows."""
    from openpyxl import Workbook
    from app.models import Account
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions_Westpac_All"
    ws.append(["Bank Account", "Date", "Narrative", "Debit Amount",
               "Credit Amount", "Balance", "Categories", "Serial"])
    ws.append(["FAKE_ACCOUNT_A", date(2026, 8, 1), "DEPOSIT-SALARY Example",
               None, 2500, 5500, "DEP", None])
    ws.append(["FAKE_ACCOUNT_B", date(2026, 8, 2), "WITHDRAWAL-OSKO PAYMENT CC Payment",
               200, None, 5300, "PAYMENT", None])
    ws.append(["FAKE_ACCOUNT_B", date(2026, 8, 3), "Coffee shop",
               8.50, None, 5291.50, "POS", None])
    buffer = io.BytesIO()
    wb.save(buffer)
    with app.app_context():
        profile = profile_bytes(buffer.getvalue(), "synthetic.xlsx")
        assert len(profile["transactions"]) == 3
        assert [r["amount"] for r in profile["transactions"]] == [
            Decimal("2500.00"), Decimal("-200.00"), Decimal("-8.50")]
        imported = import_bytes(buffer.getvalue(), "synthetic.xlsx")
        assert imported["status"] == "completed"
        assert Transaction.query.count() == 3
        assert Account.query.filter_by(display_name="Westpac: FAKE_ACCOUNT_A").count() == 1
        assert Transaction.query.filter_by(income_flag=True).count() == 1
        assert Transaction.query.filter_by(transfer_flag=True).count() == 1
        assert import_bytes(buffer.getvalue(), "synthetic.xlsx")["status"] == "unchanged"
