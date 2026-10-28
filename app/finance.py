"""Exact-money summaries; avoid treating bank credits as income without classification."""
import re
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


def effective_income(t):
    """Prefer explicit Westpac payroll markers over stale transfer classifications."""
    if t.signed_amount <= 0:
        return False
    narrative = " ".join((t.raw_description or "", t.merchant_raw or "", t.raw_type or ""))
    if re.search(r"\b(salary|payroll|wages)\b", narrative, re.I):
        return True
    return bool(t.income_flag and not t.excluded_from_spending and not t.transfer_flag)


def spending(start=None, end=None, group_by="month"):
    q = transaction_query(start, end, include_transfers=True).all()
    groups = {}
    for t in q:
        income = effective_income(t)
        if not income and (t.excluded_from_spending or t.transfer_flag):
            continue
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
        if income:
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


def spending_categories(start=None, end=None):
    """Aggregated net category expenses, excluding transfers and classified income.

    Positive refunds reduce their category's spending. Retain negative totals if
    refunds exceed charges so the API never silently loses real financial data.
    """
    from app.models import Category

    categories = {c.id: c.name for c in Category.query.all()}
    totals = {}
    for txn in transaction_query(start, end, include_transfers=True).all():
        if effective_income(txn) or txn.transfer_flag or txn.excluded_from_spending:
            continue
        label = categories.get(txn.category_id, "Uncategorised")
        totals[label] = totals.get(label, Decimal("0")) - txn.signed_amount
    return [{"category": name, "spending": money(value)}
            for name, value in sorted(totals.items(), key=lambda x: (-x[1], x[0]))]


def transaction_years():
    from sqlalchemy import extract
    years = db.session.query(extract("year", Transaction.date)).distinct().order_by(
        extract("year", Transaction.date).desc()
    ).all()
    return [int(row[0]) for row in years if row[0] is not None]


def income_audit():
    """Aggregated diagnostic without revealing account numbers or transaction narratives."""
    from sqlalchemy import func
    from app.models import ImportRun, SourceRecord

    westpac = db.session.query(Transaction).join(
        SourceRecord, SourceRecord.source_key == Transaction.source_key
    ).filter(SourceRecord.sheet.ilike("Transactions_Westpac_All%"))
    by_month = {}
    for t in westpac.all():
        month = t.date.strftime("%Y-%m")
        line = by_month.setdefault(month, {
            "westpac_rows": 0, "salary_marker_credits": 0,
            "salary_marker_amount": Decimal("0"),
            "classified_income": Decimal("0"), "classified_income_rows": 0,
            "excluded_salary_rows": 0,
        })
        line["westpac_rows"] += 1
        salary = t.signed_amount > 0 and bool(re.search(
            r"\b(salary|payroll|wages)\b", t.raw_description or "", re.I))
        if salary:
            line["salary_marker_credits"] += 1
            line["salary_marker_amount"] += t.signed_amount
            if not t.income_flag:
                line["excluded_salary_rows"] += 1
        if t.income_flag and not t.excluded_from_spending:
            line["classified_income_rows"] += 1
            line["classified_income"] += t.signed_amount
    latest = ImportRun.query.filter_by(status="completed").order_by(
        ImportRun.id.desc()).first()
    return {
        "westpac_transaction_count": westpac.count(),
        "latest_import": {
            "id": latest.id, "filename": latest.filename,
            "importer_version": latest.importer_version,
            "status": latest.status,
        } if latest else None,
        "months": [
            {**v, "month": k, "salary_marker_amount": money(v["salary_marker_amount"]),
             "classified_income": money(v["classified_income"])}
            for k, v in sorted(by_month.items())
        ],
    }


def mortgage_tracking():
    """Read actual investment mortgage, offset and calculator data from tracking sheet.

    A workbook snapshot is authoritative for historical values and cached calculated
    indicators. Projected balances extend the observed average monthly change.
    """
    from datetime import date
    from pathlib import Path
    from calendar import monthrange
    from openpyxl import load_workbook
    from flask import current_app
    from app.importer import parse_date

    source = (current_app.config.get("GRAPH_FINANCE_CACHE_PATH")
              if current_app.config.get("LIFE_DATA_SOURCE") == "onedrive"
              else current_app.config.get("SOURCE_WORKBOOK"))
    if not source:
        return dict(status="not_configured", history=[], projection=[], indicators={},
                    message="LIFE_FINANCE_XLSX_PATH is empty in the running Flask process.")
    source_path = Path(str(source).strip().strip('"'))
    if not source_path.is_file():
        alternate = source_path.with_name(source_path.stem.replace("_", " ") + source_path.suffix)
        if alternate.is_file():
            source_path = alternate
        else:
            return dict(status="source_not_found", history=[], projection=[], indicators={},
                        message="Workbook not found: " + str(source_path))
    wb = load_workbook(source_path, read_only=True, data_only=True)
    try:
        if "Net Worth Tracking" not in wb:
            return dict(status="unavailable", history=[], projection=[], indicators={},
                        message="Net Worth Tracking worksheet not found")
        ws = wb["Net Worth Tracking"]
        # Read once: read-only worksheets are slow with repeated random access.
        rows = list(ws.values)
        def label(row):
            return str(row[0] or "").strip().casefold()
        names = {label(row): i for i, row in enumerate(rows) if row and row[0] is not None}
        def match(*labels):
            for name in labels:
                if name.casefold() in names:
                    return names[name.casefold()]
            return None
        loan = match("Rocket Investment Loan", "Mortgage balance", "Home Loan", "Investment Loan")
        offset = match("WBC Choice (Offset)", "Offset balance", "Mortgage Offset")
        rate = match("Interest Rate", "Mortgage Interest Rate")
        months = match("Months Remaining")
        annual_saving = match("Annual Calculated Savings")
        total_saving = match("Total Calculated Savings")
        next_interest = match("Next Calculated Interest Charge")
        if loan is None:
            return dict(status="unavailable", history=[], projection=[], indicators={},
                        message="Could not locate Rocket Investment Loan in column A")
        def dec(row, col):
            if row is None or col >= len(rows[row]):
                return None
            value = rows[row][col]
            if value is None or isinstance(value, bool):
                return None
            try:
                v = Decimal(str(value).replace("$", "").replace(",", "").strip())
                return v if v.is_finite() else None
            except (ValueError, ArithmeticError):
                return None
        snapshots = []
        for col in range(1, len(rows[0])):
            try:
                stamp = parse_date(rows[0][col], wb.epoch)
            except (ValueError, TypeError):
                continue
            if stamp > date.today():
                continue
            principal = dec(loan, col)
            if principal is not None:
                snapshots.append((stamp, col, abs(principal)))
        snapshots.sort(key=lambda item: item[0])
        if not snapshots:
            return dict(status="unavailable", history=[], projection=[], indicators={},
                        message="No dated mortgage values were found")
        history = [dict(as_of=d.isoformat(), balance=money(p)) for d, _, p in snapshots]
        last_date, last_col, principal = snapshots[-1]
        current_rate = dec(rate, last_col)
        if current_rate is not None and current_rate > 1:
            current_rate /= Decimal(100)
        if current_rate is not None and not (0 <= current_rate <= 1):
            current_rate = None
        current_offset = dec(offset, last_col)
        remaining = dec(months, last_col)
        saved_annually = dec(annual_saving, last_col)
        saved_total = dec(total_saving, last_col)
        interest = dec(next_interest, last_col)
        # Only fall back to estimates if a formula has no cached value.
        if interest is None and current_rate is not None:
            interest = max(Decimal(0), principal - max(Decimal(0), current_offset or Decimal(0))) * current_rate / 12
        if saved_annually is None and current_rate is not None and current_offset is not None:
            saved_annually = min(principal, max(Decimal(0), current_offset)) * current_rate
        if saved_total is None and saved_annually is not None and remaining is not None:
            saved_total = saved_annually * remaining / 12
        delta = []
        for (prior_date, _, prior_balance), (following_date, _, following_balance) in zip(snapshots, snapshots[1:]):
            elapsed = (following_date - prior_date).days
            if elapsed > 0:
                delta.append((prior_balance - following_balance) * Decimal("30.4375") / elapsed)
        monthly_reduction = sum(delta, Decimal(0)) / len(delta) if delta else Decimal(0)
        future = []
        for i in range(1, 13):
            year = last_date.year + (last_date.month - 1 + i) // 12
            month = (last_date.month - 1 + i) % 12 + 1
            day = min(last_date.day, monthrange(year, month)[1])
            future.append(dict(as_of=date(year, month, day).isoformat(),
                               balance=money(max(Decimal(0), principal - monthly_reduction * i))))
        return dict(
            status="ok", history=history, projection=future,
            indicators=dict(principal=money(principal), as_of=last_date.isoformat(),
                interest_rate=str(current_rate) if current_rate is not None else None,
                offset=money(current_offset), months_remaining=str(remaining) if remaining is not None else None,
                annual_calculated_savings=money(saved_annually),
                total_calculated_savings=money(saved_total),
                next_month_interest_estimate=money(interest),
                monthly_offset_interest_saving=money(saved_annually / 12) if saved_annually is not None else None,
                daily_offset_interest_saving=money(saved_annually / 365) if saved_annually is not None else None,
                average_monthly_principal_reduction=money(monthly_reduction)),
            assumptions="Mortgage balance is sourced from Rocket Investment Loan; indicators use the most recent cached workbook calculations when available. Dashed projection extrapolates average observed principal change over 12 months.")
    finally:
        wb.close()
