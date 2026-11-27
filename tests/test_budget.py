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
