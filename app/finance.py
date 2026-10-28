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
    """Recognise explicit payroll credits even if an older import stored false flags."""
    if t.signed_amount <= 0 or t.excluded_from_spending or t.transfer_flag:
        return False
    if t.income_flag:
        return True
    return bool(re.search(r"\b(salary|payroll|wages)\b",
                          t.raw_description or "", re.I))


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
        if effective_income(t):
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
    for txn in transaction_query(start, end, include_transfers=False).all():
        if effective_income(txn):
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
    """Read source-verified mortgage observations from the configured workbook.

    Values are deliberately omitted when a label cannot be identified reliably.
    The workbook is the source of truth; no hard-coded account figures.
    """
    from datetime import date
    from pathlib import Path
    from flask import current_app
    from openpyxl import load_workbook
    from app.importer import parse_date
    source = current_app.config.get("SOURCE_WORKBOOK")
    if not source or not Path(source).is_file():
        return {"status": "not_configured", "history": [], "projection": [],
                "indicators": {}, "message": "Configure LIFE_FINANCE_XLSX_PATH to read mortgage data."}
    wb = load_workbook(source, read_only=True, data_only=True)
    try:
        if "Net Worth Tracking" not in wb:
            return {"status": "unavailable", "history": [], "projection": [],
                    "indicators": {}, "message": "Net Worth Tracking sheet missing."}
        ws = wb["Net Worth Tracking"]
        labels = [(i, str(ws.cell(i, 1).value or "").strip().lower())
                  for i in range(1, ws.max_row + 1)]
        def pick(*patterns):
            for pattern in patterns:
                hits = [row for row, label in labels if re.search(pattern, label, re.I)]
                if len(hits) == 1:
                    return hits[0]
            return None
        # Exclude offset/equity/net-worth totals: only an outstanding loan balance qualifies.
        loan_row = pick(r"^(?:investment property |home |property )?(?:mortgage|home loan|housing loan)(?: balance| amount| outstanding)?$",
                        r"^(?:mortgage|home loan|loan balance|mortgage outstanding)\\b")
        if loan_row is None:
            return {"status": "unavailable", "history": [], "projection": [],
                    "indicators": {}, "message": "Mortgage principal row could not be uniquely identified in column A."}
        def number(value):
            if value is None or isinstance(value, bool): return None
            try:
                result = Decimal(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
                return result if result.is_finite() else None
            except Exception: return None
        rate_row = pick(r"^(?:mortgage |home loan )?(?:interest rate|annual interest rate|rate)(?: \\(%)\\)?$")
        offset_row = pick(r"^(?:mortgage )?offset(?: account)?(?: balance)?$")
        remaining_row = pick(r"^(?:months remaining|remaining months|loan term remaining \\(months\\))$")
        payment_row = pick(r"^(?:mortgage )?(?:repayment|monthly repayment|monthly payment|fortnightly repayment)$")
        history, columns = [], []
        for col in range(2, ws.max_column + 1):
            try: d = parse_date(ws.cell(1, col).value, wb.epoch)
            except (ValueError, TypeError): continue
            if d > date.today(): continue
            raw = number(ws.cell(loan_row, col).value)
            if raw is None: continue
            columns.append(col)
            history.append({"as_of": d.isoformat(), "balance": money(abs(raw))})
        history.sort(key=lambda item: item["as_of"])
        if not history:
            return {"status": "unavailable", "history": [], "projection": [],
                    "indicators": {}, "message": "No dated mortgage balances found."}
        latest_day = history[-1]["as_of"]
        latest_col = next(c for c in columns if str(parse_date(ws.cell(1,c).value, wb.epoch)) == latest_day)
        def val(row): return number(ws.cell(row,latest_col).value) if row else None
        rate, offset, months, payment = val(rate_row), val(offset_row), val(remaining_row), val(payment_row)
        if rate is not None and rate > 1: rate /= 100
        if rate is not None and not (0 <= rate <= 1): rate = None
        principal = Decimal(history[-1]["balance"])
        offset = abs(offset) if offset is not None else None
        charge = max(Decimal(0),principal-(offset or Decimal(0)))*rate/Decimal(12) if rate is not None else None
        without_offset = principal*rate/Decimal(12) if rate is not None else None
        daily_saving = min(principal,offset)*rate/Decimal(365) if rate is not None and offset is not None else None
        monthly_saving = without_offset-charge if without_offset is not None and offset is not None else None
        # Linear continuation uses observed average monthly principal reduction,
        # normalised for unequal snapshot spacing. Never extrapolate upward debt as amortisation.
        from datetime import datetime
        from calendar import monthrange
        def days(v): return datetime.fromisoformat(v["as_of"]).date().toordinal()
        increments = [(Decimal(history[i-1]["balance"])-Decimal(history[i]["balance"]))*
                       Decimal("30.4375")/Decimal(days(history[i])-days(history[i-1]))
                       for i in range(1,len(history)) if days(history[i])>days(history[i-1])]
        average = sum(increments, Decimal(0))/len(increments) if increments else Decimal(0)
        projected = []
        y,m = map(int,latest_day.split("-")[:2]); day = int(latest_day[-2:])
        for index in range(1,13):
            yy=y+(m-1+index)//12; mm=(m-1+index)%12+1
            dd=min(day,monthrange(yy,mm)[1])
            projected.append({"as_of":f"{yy:04d}-{mm:02d}-{dd:02d}",
                              "balance":money(max(Decimal(0),principal-average*index))})
        return {"status":"ok", "history":history, "projection":projected,
                "indicators":{"principal":money(principal),"as_of":latest_day,
                 "interest_rate":str(rate) if rate is not None else None,
                 "offset":money(offset),"months_remaining":str(months) if months is not None else None,
                 "repayment":money(payment), "next_month_interest_estimate":money(charge),
                 "monthly_offset_interest_saving":money(monthly_saving),
                 "daily_offset_interest_saving":money(daily_saving),
                 "average_monthly_principal_reduction":money(average)},
                "assumptions":"Projection: average observed monthly principal change, linear; interest: nominal rate / 12, constant balance and offset. Actual bank daily interest differs."}
    finally:
        wb.close()
