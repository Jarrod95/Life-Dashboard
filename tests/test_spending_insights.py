"""Synthetic spending regression tests: never rely on a personal workbook."""
from datetime import date
from decimal import Decimal

import pytest
from app import create_app, db
from app.models import Category, Transaction
from app.finance_insights import period, summarize, recurring, opportunities


@pytest.fixture
def app(tmp_path):
    application = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "spending.sqlite")})
    yield application


def seed():
    dining = Category(name="Restaurants",category_type="expense")
    housing = Category(name="Strata",category_type="expense")
    db.session.add_all([dining,housing]);db.session.flush()
    rows = [
        ("c1",date(2025,12,20),"-12.30",dining.id,"Cafe"),
        ("c2",date(2026,1,10),"-25.10",dining.id,"Cafe"),
        ("c3",date(2026,2,10),"-25.10",dining.id,"Cafe"),
        ("c4",date(2026,3,10),"-25.10",dining.id,"Cafe"),
        ("p1",date(2026,3,11),"-1200.00",housing.id,"Strata"),
        ("i1",date(2026,3,12),"4000.00",None,"Payroll"),
        ("b1",date(2026,3,13),"-60.00",None,"Afterpay"),
        ("t1",date(2026,3,14),"-500.00",None,"Savings transfer"),
    ]
    for key,day,amount,category,merchant in rows:
        db.session.add(Transaction(source_key=key,date=day,signed_amount=Decimal(amount),
            category_id=category,merchant_normalized=merchant,raw_description=merchant,
            income_flag=key=="i1", transfer_flag=key=="t1",
            excluded_from_spending=key=="t1"))
    db.session.commit()


def test_period_bounds_and_default(app):
    with app.app_context():
        seed()
        p = period(today=date(2028,1,1))
        assert p["year"] == 2026 and p["start"] == date(2026,1,1)
        assert period(2024,2,today=date(2028,1,1))["end"] == date(2024,2,29)
        assert period(2026,12)["end"] == date(2026,12,31)
        with pytest.raises(ValueError):
            period(2026,13)


def test_canonical_money_and_warnings(app):
    with app.app_context():
        seed()
        s=summarize(period(2026,3,today=date(2026,4,1)))
        assert s["total_consumption_aud"] == "25.10"
        assert s["discretionary_aud"] == "25.10"
        assert s["cash_debits_aud"] == "1785.10"
        assert any("BNPL" in x for x in s["warnings"])
        assert s["categories"] == [{"category":"Restaurants","spending":"25.10"}]
        assert all(x["category"]!="Strata" for x in opportunities(s))


def test_recurring_requires_three_transactions(app):
    with app.app_context():
        seed()
        s=summarize(period(2026,today=date(2027,1,1)))
        recurrence=recurring(s)
        assert len(recurrence)==1
        assert recurrence[0]["merchant"]=="cafe"
        assert recurrence[0]["cadence"]=="monthly"
        assert recurrence[0]["occurrences"]==3


def test_api_period_consistency(app):
    with app.app_context():
        seed()
        client=app.test_client()
        query="?year=2026&month=3"
        summary=client.get("/api/v1/finance/spending/summary"+query).json["data"]
        category=client.get("/api/v1/finance/spending/categories"+query).json["data"]
        merchants=client.get("/api/v1/finance/spending/merchants"+query).json["data"]
        assert summary["total_consumption_aud"]=="25.10"
        assert category==[{"category":"Restaurants","spending":"25.10"}]
        assert sum(Decimal(x["spend_aud"]) for x in merchants)==Decimal("25.10")
        tx=client.get("/api/v1/finance/transactions"+query).json
        assert tx["total"]==5
        assert client.get("/api/v1/finance/spending/summary?year=2026&month=99").status_code==400
