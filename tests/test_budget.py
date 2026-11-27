from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from openpyxl import Workbook

from app.budget import parse_budget, period_dates, months_between, actual_key


def fixture():
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    for cell, value in {"A1":"BUDGET 2026-27", "A3":"Net Income", "G4":"Yearly",
                        "A5":"Salary", "G5":60000, "A7":"Total", "G7":60000,
                        "A10":"Expenses", "G11":"Yearly", "A12":"Groceries", "G12":6000,
                        "A24":"Investment Property", "A25":"Mortgage", "G25":24000,
                        "A29":"Total Expenses", "G29":30000, "A31":"Savings 10%",
                        "G31":6000, "P5":90000}.items():
        ws[cell] = value
    return wb


def test_source_sections_and_cached_values():
    wb = fixture()
    lines, warnings = parse_budget(wb)
    assert not warnings
    assert [(x["kind"],x["annual"]) for x in lines] == [
        ("income",Decimal(60000)),("expense",Decimal(6000)),("property_expense",Decimal(24000))]
    wb["Budget"]["G12"] = None
    lines, warnings = parse_budget(wb)
    assert not lines and warnings


def test_fiscal_year_and_partial_month():
    assert period_dates(2026,2) == (date(2027,2,1),date(2027,2,28))
    assert months_between(date(2026,7,1),date(2026,8,31)) == 2
    assert months_between(date(2026,11,1),date(2026,11,15)) == Decimal("0.5")


def tx(amount, narrative, transfer=False):
    return SimpleNamespace(signed_amount=Decimal(amount),raw_description=narrative,
                           merchant_normalized="",merchant_raw="",raw_type="",
                           transfer_flag=transfer,excluded_from_spending=transfer,income_flag=False)


def test_mortgage_and_transfer_reconciliation():
    assert actual_key(tx("-100","PAYMENT BY AUTHORITY TO WESTPAC BANKCORP DIRECT"),"PAYMENT") == "mortgage"
    assert actual_key(tx("-50","INTEREST"),"INT") == "excluded"
    assert actual_key(tx("-100","internal transfer",True),"Groceries") == "excluded"
    assert actual_key(tx("-20","merchant"),"Groceries") == "groceries"
    assert actual_key(tx("-20","Afterpay"),"Other shopping") == "bnpl"
    assert actual_key(tx("100","DEPOSIT-SALARY"),"DEP") == "salary"


def test_import_and_comparison_integration(tmp_path):
    from io import BytesIO
    from app import create_app
    from app.importer import import_bytes
    from app.budget import comparison
    from app.models import BudgetLine

    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "budget.sqlite")})
    wb = fixture()
    txs = wb.create_sheet("Transactions_2026_NAB")
    txs.append(["Date", "Amount", "Account Number", "Transaction Type",
                "Transaction Details", "Category", "Merchant Name"])
    txs.append([date(2026, 7, 1), -50, "test", "purchase", "Food", "Groceries", "Grocer"])
    txs.append([date(2026, 7, 15), -20, "test", "purchase", "Meal", "Dining", "Cafe"])
    txs.append([date(2026, 7, 31), 5000, "test", "salary", "Salary", "Income", "Employer"])
    txs.append([date(2026, 7, 31), -100, "test", "transfer", "Internal transfer", "Transfers", "Internal"])
    output = BytesIO()
    wb.save(output)
    with app.app_context():
        first = import_bytes(output.getvalue(), "synthetic.xlsx")
        assert first["counts"]["budgets"] == 3
        import_bytes(output.getvalue(), "synthetic.xlsx", force=True)
        assert BudgetLine.query.count() == 3
        report = comparison(2026, 7, today=date(2026, 8, 1))
        assert report["actual"]["target"] == "2500.00"
        assert report["actual"]["spending"] == "70.00"
        assert report["actual"]["unallocated"] == "20.00"
        assert report["actual"]["income"] == "5000.00"
        assert report["actual"]["excluded_debits"] == "100.00"
        assert report["plan"]["monthly_surplus"] == "2500.00"
        mortgage = next(x for x in report["lines"] if x["name"] == "Mortgage")
        assert mortgage["actual"] is None
        future = comparison(2026, 8, today=date(2026, 8, 1))
        assert future["actual"]["spending"] is None
    client = app.test_client()
    assert client.get("/finance/budget?fiscal_year=2026&month=7").status_code == 200
    assert client.get("/api/v1/finance/budget/comparison?fiscal_year=2026&month=7").status_code == 200
    assert client.get("/api/v1/finance/budget/comparison?month=13").status_code == 400
