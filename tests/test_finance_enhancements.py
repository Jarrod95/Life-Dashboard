"""Regression tests for source-backed mortgage summaries and Westpac payroll credits."""
from datetime import date
from decimal import Decimal
from openpyxl import Workbook
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "finance-test.sqlite"),
    })
    yield application

from app.finance import mortgage_tracking, spending
from app.importer import import_bytes


def test_mortgage_source_history_and_estimates(app, tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Net Worth Tracking"
    ws["A54"] = "Mortgage balance"
    ws["A64"] = "Interest rate"
    ws["A65"] = "Offset balance"
    ws["A66"] = "Months remaining"
    for col, month, loan in [(2, 1, 400000), (3, 2, 398000), (4, 3, 396000)]:
        ws.cell(1, col, date(2026, month, 1))
        ws.cell(54, col, loan)
        ws.cell(64, col, 5.64)
        ws.cell(65, col, 60000)
        ws.cell(66, col, 320)
    path = tmp_path / "financial.xlsx"
    wb.save(path)
    with app.app_context():
        app.config["SOURCE_WORKBOOK"] = str(path)
        result = mortgage_tracking()
        assert result["status"] == "ok"
        assert len(result["history"]) == 3
        assert len(result["projection"]) == 12
        assert result["indicators"]["principal"] == "396000.00"
        assert result["indicators"]["interest_rate"] == str(Decimal("0.0564"))
        assert result["indicators"]["months_remaining"] == "320"
        assert Decimal(result["indicators"]["monthly_offset_interest_saving"]) > 0


def test_westpac_salary_credit_is_income(app):
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions_Westpac_All"
    ws.append(["Bank Account", "Date", "Narrative", "Debit Amount",
               "Credit Amount", "Balance", "Categories", "Serial"])
    ws.append(["A", date(2026, 3, 1), "DEPOSIT-SALARY Payroll",
               None, 4000, None, "DEP", None])
    ws.append(["A", date(2026, 3, 2), "Groceries",
               80, None, None, "Food", None])
    out = BytesIO()
    wb.save(out)
    with app.app_context():
        import_bytes(out.getvalue(), "financial.xlsx")
        rows = spending(group_by="month")
        march = next(row for row in rows if row["label"] == "2026-03")
        assert march["income"] == "4000.00"
        assert march["spending"] == "80.00"


def test_stale_transfer_flag_does_not_suppress_payroll(app):
    from app import db
    from app.models import Transaction
    from datetime import date
    with app.app_context():
        db.session.add(Transaction(
            source_key="historical-payroll", date=date(2026, 5, 14),
            signed_amount=Decimal("3600"), raw_description="SALARY Payroll",
            transfer_flag=True, excluded_from_spending=True, income_flag=False,
        ))
        db.session.add(Transaction(
            source_key="internal-transfer", date=date(2026, 5, 14),
            signed_amount=Decimal("500"), raw_description="Internal transfer",
            transfer_flag=True, excluded_from_spending=True, income_flag=False,
        ))
        db.session.commit()
        may = next(x for x in spending(group_by="month") if x["label"] == "2026-05")
        assert may["income"] == "3600.00"
        assert may["spending"] == "0.00"


def test_missing_workbook_reports_actual_path(app, tmp_path):
    from app.finance import mortgage_tracking
    missing = tmp_path / "Financial_Dashboard.xlsx"
    with app.app_context():
        app.config["SOURCE_WORKBOOK"] = str(missing)
        result = mortgage_tracking()
        assert result["status"] == "source_not_found"
        assert str(missing) in result["message"]


def test_underscore_filename_fallback(app, tmp_path):
    from app.finance import mortgage_tracking
    wb = Workbook()
    ws = wb.active
    ws.title = "Net Worth Tracking"
    ws["A54"] = "Mortgage balance"
    ws["B1"] = date(2026, 3, 1)
    ws["B54"] = 400000
    actual = tmp_path / "Financial Dashboard.xlsx"
    wb.save(actual)
    with app.app_context():
        app.config["SOURCE_WORKBOOK"] = str(tmp_path / "Financial_Dashboard.xlsx")
        result = mortgage_tracking()
        assert result["status"] == "ok"
        assert result["indicators"]["principal"] == "400000.00"


def test_real_tracking_sheet_layout(app, tmp_path):
    """Match the actual workbook row names with synthetic financial amounts."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Net Worth Tracking"
    names = {14: "WBC Choice (Offset)", 55: "Rocket Investment Loan",
             65: "Interest Rate ", 66: "Months Remaining",
             67: "Annual Calculated Savings", 68: "Total Calculated Savings",
             69: "Next Calculated Interest Charge"}
    for row, name in names.items():
        ws.cell(row, 1, name)
    for col, month, debt in [(2, 8, 400000), (3, 9, 398000), (4, 10, 396000)]:
        ws.cell(1, col, date(2026, month, 21))
        ws.cell(14, col, 60000)
        ws.cell(55, col, debt)
        ws.cell(65, col, 0.06)
        ws.cell(66, col, 320)
        ws.cell(67, col, 3600)
        ws.cell(68, col, 96000)
        ws.cell(69, col, 1680)
    path = tmp_path / "Financial Dashboard.xlsx"
    wb.save(path)
    with app.app_context():
        app.config["SOURCE_WORKBOOK"] = str(path)
        result = mortgage_tracking()
        assert result["status"] == "ok"
        assert len(result["history"]) == 3
        assert len(result["projection"]) == 12
        assert result["indicators"]["principal"] == "396000.00"
        assert result["indicators"]["offset"] == "60000.00"
        assert result["indicators"]["annual_calculated_savings"] == "3600.00"
        assert result["indicators"]["total_calculated_savings"] == "96000.00"
        assert result["indicators"]["next_month_interest_estimate"] == "1680.00"
