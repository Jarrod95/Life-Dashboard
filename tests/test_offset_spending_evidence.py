"""Synthetic tests for the offset forecast and improved savings evidence."""
from datetime import date
from decimal import Decimal

from app.offset_projection import project_offset


def test_offset_empty_history():
    data = project_offset([])
    assert data["status"] == "no_data"
    assert data["projection"] == []


def test_offset_projection_calendar_edges_and_exact_money():
    data = project_offset([
        (date(2026, 1, 31), Decimal("1000.00")),
        (date(2026, 2, 28), Decimal("1100.00")),
        (date(2026, 3, 31), Decimal("1200.00")),
    ])
    assert data["status"] == "ok"
    assert len(data["history"]) == 3
    assert len(data["projection"]) == 12
    assert data["projection"][0]["as_of"] == "2026-04-30"
    assert data["projection"][-1]["as_of"] == "2027-03-31"
    assert Decimal(data["projected_12mo_aud"]) > Decimal("1200.00")


def test_offset_does_not_project_negative_balance():
    data = project_offset([(date(2026, 1, 1), 200), (date(2026, 2, 1), 100)])
    assert all(Decimal(p["balance_aud"]) >= 0 for p in data["projection"])


def test_opportunities_evidence_with_coverage(app):
    from app import db
    from app.models import Category, Transaction
    from app.finance_insights import period, opportunities, summarize
    with app.app_context():
        cat=Category(name="Restaurants",category_type="expense")
        db.session.add(cat);db.session.flush()
        for i,(day,amount) in enumerate([
            (date(2026,1,6), "-40"), (date(2026,2,6), "-40"),
            (date(2026,3,6), "-40"), (date(2026,4,6), "-60"),
            (date(2026,4,9), "-70"), (date(2026,4,12), "-80"),
        ]):
            db.session.add(Transaction(source_key="insight-"+str(i),date=day,
                signed_amount=Decimal(amount),category_id=cat.id,
                merchant_normalized="Restaurant",raw_description="Restaurant"))
        db.session.commit()
        selected=period(2026,4,today=date(2026,5,1))
        items=opportunities(summarize(selected))
        assert len(items)==1
        assert items[0]["average_ticket_aud"]=="70.00"
        assert items[0]["baseline_monthly_aud"]=="40.00"
        assert items[0]["change_pct"]==425.0
        assert items[0]["signal"]=="increasing spend"
        assert items[0]["transactions"]==3
