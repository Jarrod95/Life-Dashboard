"""Exact-money summaries; avoid treating bank credits as income without classification."""
from decimal import Decimal
from app import db
from app.models import NetWorthSnapshot, Transaction, AccountValuation, Account


def money(value):
    return str(Decimal(value).quantize(Decimal("0.01"))) if value is not None else None


def snapshot_json(snapshot):
    if snapshot is None:
        return None
    return dict(id=snapshot.id, as_of=snapshot.as_of_date.isoformat(),
                reported=money(snapshot.source_net_worth),
                reconstructed=money(snapshot.calculated_net_worth),
                reconciliation_delta=money(snapshot.reconciliation_delta))


def timeline(start=None, end=None):
    query = NetWorthSnapshot.query
    if start:
        query = query.filter(NetWorthSnapshot.as_of_date >= start)
    if end:
        query = query.filter(NetWorthSnapshot.as_of_date <= end)
    return [snapshot_json(x) for x in query.order_by(NetWorthSnapshot.as_of_date).all()]


def summary(as_of=None):
    q = NetWorthSnapshot.query
    if as_of:
        q = q.filter(NetWorthSnapshot.as_of_date <= as_of)
    latest = q.order_by(NetWorthSnapshot.as_of_date.desc()).first()
    prior = None
    if latest:
        prior = NetWorthSnapshot.query.filter(
            NetWorthSnapshot.as_of_date < latest.as_of_date
        ).order_by(NetWorthSnapshot.as_of_date.desc()).first()
    current = latest.source_net_worth if latest else None
    previous = prior.source_net_worth if prior else None
    return dict(latest=snapshot_json(latest), previous=snapshot_json(prior),
                change=money(current - previous) if current is not None and previous is not None else None)


def transaction_query(start=None, end=None, category=None, merchant=None, account=None,
                      include_transfers=True, search=None):
    q = Transaction.query
    if start:
        q = q.filter(Transaction.date >= start)
    if end:
        q = q.filter(Transaction.date <= end)
    if category:
        q = q.filter(Transaction.category_id == category)
    if merchant:
        q = q.filter(Transaction.merchant_normalized.ilike(f"%{merchant}%"))
    if search:
        q = q.filter(db.or_(Transaction.raw_description.ilike(f"%{search}%"),
                            Transaction.merchant_normalized.ilike(f"%{search}%")))
    if account:
        q = q.filter(Transaction.account_id == account)
    if not include_transfers:
        q = q.filter(Transaction.excluded_from_spending.is_(False))
    return q


def transaction_json(t):
    return dict(id=t.id, date=t.date.isoformat(), amount=money(t.signed_amount),
                merchant=t.merchant_normalized, description=t.raw_description,
                category_id=t.category_id, account_id=t.account_id,
                transfer=t.transfer_flag, income=t.income_flag,
                excluded=t.excluded_from_spending)


def spending(start=None, end=None, group_by="month"):
    q = transaction_query(start, end, include_transfers=False).all()
    groups = {}
    for t in q:
        if group_by == "month":
            key = t.date.strftime("%Y-%m")
        elif group_by == "year":
            key = str(t.date.year)
        elif group_by == "category":
            key = str(t.category_id or "uncategorised")
        else:
            key = t.merchant_normalized or "Unknown"
        bucket = groups.setdefault(key, {"income": Decimal("0"), "spending": Decimal("0")})
        # Positive values not flagged as income are credits/refunds, reducing spending.
        if t.income_flag:
            bucket["income"] += t.signed_amount
        else:
            bucket["spending"] -= t.signed_amount
    return [dict(label=k, income=money(v["income"]), spending=money(v["spending"]),
                 net=money(v["income"]-v["spending"])) for k, v in sorted(groups.items())]


def latest_valuations():
    snap = NetWorthSnapshot.query.order_by(NetWorthSnapshot.as_of_date.desc()).first()
    if snap is None:
        return []
    vals = db.session.query(AccountValuation, Account).join(Account).filter(
        AccountValuation.snapshot_id == snap.id
    ).order_by(AccountValuation.category, Account.display_name).all()
    return [dict(account=a.display_name, category=v.category, kind=v.kind,
                 amount=money(v.amount_aud)) for v, a in vals]


def mortgage_scenario(principal, annual_rate, offset, payment, extra=Decimal("0"),
                      monthly_topup=Decimal("0"), max_months=600):
    """End-of-month payments, monthly interest, offset capped at principal."""
    args = [Decimal(str(x)) for x in (principal, annual_rate, offset, payment, extra, monthly_topup)]
    p, rate, balance, repayment, additional, topup = args
    if p < 0 or rate < 0 or rate > 1 or balance < 0 or repayment <= 0 or additional < 0 or topup < 0:
        raise ValueError("Invalid scenario: use non-negative balances/rate and positive payment")
    rate_month = rate / Decimal(12)
    interest_total = Decimal(0)
    for month in range(max_months + 1):
        if p <= 0:
            return {"months": month, "total_interest": money(interest_total),
                    "remaining_principal": "0.00", "paid_off": True}
        if month == max_months:
            break
        effective = max(Decimal(0), p - balance)
        interest = effective * rate_month
        if repayment + additional <= interest:
            raise ValueError("Payment does not cover interest; negative amortisation")
        interest_total += interest
        p = max(Decimal(0), p + interest - repayment - additional)
        balance += topup
    return {"months": max_months, "total_interest": money(interest_total),
            "remaining_principal": money(p), "paid_off": False}
