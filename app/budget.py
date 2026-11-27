"""Workbook budget import and cash-flow comparison (AUD, current-plan basis)."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from app import db
from app.finance import money, effective_income
from app.models import BudgetLine, Category, ImportRun, Transaction

ZERO = Decimal(0)


def parse_budget(wb):
    """Validate section boundaries, annual column, FY and cached numeric amounts.

    Never combine the gross-income/tax illustration on the right with the net
    cash-flow plan on the left. Do not publish a partial replacement plan.
    """
    if "Budget" not in wb:
        return [], ["Budget sheet missing"]
    ws = wb["Budget"]
    rows = list(ws.iter_rows(min_col=1, max_col=7, max_row=min(ws.max_row, 300),
                             values_only=True))
    title = str(rows[0][0] or "").strip() if rows else ""
    match = re.fullmatch(r"BUDGET\s+(\d{4})\s*[-–/]\s*(\d{2}|\d{4})", title, re.I)
    if not match:
        return [], ["Budget fiscal year title not recognised"]
    year = int(match[1])
    if not 1900 <= year <= 2099 or int(match[2]) not in (year + 1, (year + 1) % 100):
        return [], ["Budget fiscal year invalid"]
    lines, warnings, seen = [], [], set()
    kind = None
    header_ok = False
    finished = False
    for i, row in enumerate(rows, 1):
        name = str(row[0] or "").strip()
        label = name.casefold()
        if label in ("net income", "expenses"):
            kind = "income" if label == "net income" else "expense"
            header_ok = False
            continue
        if label == "investment property" and kind in ("expense", "property_expense") and row[6] is None:
            kind = "property_expense"
            continue
        if label in ("total", "total expenses"):
            if label == "total expenses":
                finished = True
                break
            kind = None
            continue
        if kind is None:
            continue
        if str(row[6] or "").strip().casefold() == "yearly":
            header_ok = True
            continue
        if not name:
            continue
        if not header_ok:
            warnings.append(f"Budget row {i}: annual header not verified")
            continue
        try:
            if row[6] is None or isinstance(row[6], bool):
                raise ValueError
            annual = Decimal(str(row[6]))
            if not annual.is_finite() or annual < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            warnings.append(f"Budget G{i}: missing or invalid cached annual amount")
            continue
        if (kind, label) in seen:
            warnings.append(f"Budget row {i}: duplicate budget line")
            continue
        seen.add((kind, label))
        lines.append(dict(fiscal_year=year, name=name, kind=kind, annual=annual, row=i))
    if not finished or not {"income", "expense"} <= {x["kind"] for x in lines}:
        warnings.append("Budget income/expense sections incomplete")
    return ([], warnings) if warnings else (lines, [])


def save_budget(lines, run_id):
    if not lines:
        return
    year = lines[0]["fiscal_year"]
    BudgetLine.query.filter_by(fiscal_year=year).delete()
    for line in lines:
        annual = line["annual"]
        db.session.add(BudgetLine(source_key=f"budget:{year}:G{line['row']}",
            source_run_id=run_id, fiscal_year=year, name=line["name"], kind=line["kind"],
            frequency="yearly", base_amount=annual, annual_equivalent=annual,
            monthly_equivalent=annual / 12, provenance=f"Budget!G{line['row']}"))


# Deliberately narrow aliases. Unmatched transactions remain visible rather than
# being allocated by amount or assumed to be groceries/household bills.
def plan_key(name, kind):
    name = name.casefold()
    if kind == "income":
        return "rent_income" if "property" in name or "rent" in name else "salary" if "cancer institute" in name or "salary" in name else None
    rules = (
        ("rent", "rent"), ("electricity", "electricity"), ("internet", "internet"),
        ("inernet", "internet"), ("gym", "gym"), ("petrol", "fuel"),
        ("car insurance", "car_insurance"), ("registration", "registration"),
        ("servicing", "service"), ("health insurance", "health_insurance"),
        ("mobile", "mobile"), ("chatgpt", "chatgpt"), ("groceries", "groceries"),
        ("mortgage", "mortgage"), ("strata", "strata"), ("water", "water"),
        ("counci", "rates"),
    )
    return next((key for fragment, key in rules if fragment in name), None)


def actual_key(t, category):
    text = " ".join((t.raw_description or "", t.merchant_normalized or "",
                     t.merchant_raw or "")).casefold()
    cat = category.casefold().strip()
    if t.signed_amount > 0 and re.search(r"\b(salary|payroll|wages)\b", text):
        return "salary"
    if t.signed_amount > 0 and ("rent" in text and ("deposit" in text or cat in ("rental income", "rent income"))):
        return "rent_income"
    # Match the payer-side mortgage debit; its corresponding loan-account
    # credit and separately posted interest are not additional cash expenses.
    if t.signed_amount < 0 and ("payment by authority to westpac bankcorp direct" in text
                                or cat == "mortgage repayment"):
        return "mortgage"
    if t.transfer_flag or t.excluded_from_spending or cat in ("internal transfers", "transfer", "transfers"):
        return "excluded"
    if cat == "int" or text.strip() == "interest":
        return "excluded"
    if effective_income(t):
        return "other_income"
    if "afterpay" in text or "zip pay" in text or "zippay" in text:
        return "bnpl"
    rules = (
        (("origin energy",), "electricity"), (("superloop",), "internet"),
        (("anytime fitness",), "gym"), (("budget direct",), "car_insurance"),
        (("service nsw registration", "vehicle registration", "ctp insurance"), "registration"),
        (("mycar",), "service"), (("unihealth", "uni health"), "health_insurance"),
        (("amaysim",), "mobile"), (("chatgpt", "openai"), "chatgpt"),
        (("deft payments", "strata levies"), "strata"), (("yarra valley water", "yarra water"), "water"),
        (("darebin",), "rates"),
    )
    if t.signed_amount < 0 or cat == "refund":
        for fragments, key in rules:
            if any(fragment in text for fragment in fragments):
                return key
        if cat in ("rent", "rent & housing", "residential rent"):
            return "rent"
        if cat == "fuel":
            return "fuel"
        if cat == "groceries":
            return "groceries"
        if cat in ("rates & body corporate", "strata"):
            return "strata" if "strata" in text else None
        # Westpac POS rows lack the curated NAB category.
        if cat == "pos" and re.search(r"\b(woolworths|coles|aldi)\b", text) and not re.search(r"petrol|fuel|ampol|metro fuel", text):
            return "groceries"
    return None


def period_dates(year, month):
    if month is None:
        return date(year, 7, 1), date(year + 1, 6, 30)
    calendar_year = year if month >= 7 else year + 1
    return date(calendar_year, month, 1), date(calendar_year, month, monthrange(calendar_year, month)[1])


def months_between(start, end):
    if not end or end < start:
        return ZERO
    result = ZERO
    for month in (7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6):
        for y in range(start.year, end.year + 1):
            first = date(y, month, 1)
            days = monthrange(y, month)[1]
            last = date(y, month, days)
            overlap = (min(end, last) - max(start, first)).days + 1
            if overlap > 0:
                result += Decimal(overlap) / days
    return result


def comparison(fiscal_year=None, month=None, today=None):
    today = today or date.today()
    years = sorted({b.fiscal_year for b in BudgetLine.query.all() if b.fiscal_year}, reverse=True)
    if fiscal_year not in (None, ""):
        try:
            fiscal_year = int(fiscal_year)
        except (TypeError, ValueError):
            raise ValueError("Invalid fiscal_year")
        if not 1900 <= fiscal_year <= 2099:
            raise ValueError("Invalid fiscal_year")
    if month in (None, "", "all"):
        month = None
    else:
        try:
            month = int(month)
        except (TypeError, ValueError):
            raise ValueError("Invalid month")
        if not 1 <= month <= 12:
            raise ValueError("Invalid month")
    current_fy = today.year if today.month >= 7 else today.year - 1
    year = fiscal_year or (current_fy if current_fy in years else years[0] if years else current_fy)
    base = dict(year=year, years=years, month=month, status="unavailable",
                warnings=[])
    lines = BudgetLine.query.filter_by(fiscal_year=year).order_by(BudgetLine.id).all()
    if not lines:
        base["warnings"] = ["No validated budget for this financial year. Sync or import the workbook with saved formula values."]
        return base
    start, end = period_dates(year, month)
    latest = Transaction.query.filter(Transaction.date <= today).order_by(Transaction.date.desc()).first()
    first = Transaction.query.order_by(Transaction.date).first()
    cutoff = min(end, today, latest.date) if latest and first.date <= end else None
    coverage_start = max(start, first.date) if first else start
    covered = months_between(coverage_start, cutoff)
    has_data = bool(covered > 0)
    factor = covered / 12
    cats = {c.id: c.name for c in Category.query.all()}
    keyed = defaultdict(list)
    for line in lines:
        key = plan_key(line.name, line.kind)
        if key:
            keyed[key].append(line.id)
    actuals, counts, unmatched = defaultdict(Decimal), defaultdict(int), defaultdict(Decimal)
    observed_income = other_income = excluded_debits = bnpl = other_credits = ZERO
    monthly = defaultdict(lambda: defaultdict(Decimal))
    if has_data:
        for t in Transaction.query.filter(Transaction.date >= coverage_start, Transaction.date <= cutoff).all():
            amount = Decimal(t.signed_amount)
            category = cats.get(t.category_id, "Uncategorised")
            key = actual_key(t, category)
            stamp = t.date.strftime("%Y-%m")
            if key == "excluded":
                if amount < 0:
                    excluded_debits -= amount
                continue
            if key == "bnpl":
                bnpl -= amount
                continue
            if key in ("salary", "rent_income", "other_income"):
                if amount > 0:
                    observed_income += amount
                    if len(keyed[key]) == 1:
                        actuals[keyed[key][0]] += amount
                        counts[keyed[key][0]] += 1
                    else:
                        other_income += amount
                continue
            if amount > 0 and category.casefold() != "refund":
                other_credits += amount
                continue
            if len(keyed[key]) == 1:
                actuals[keyed[key][0]] -= amount
                counts[keyed[key][0]] += 1
                monthly[stamp]["matched"] -= amount
            else:
                unmatched[category] -= amount
                monthly[stamp]["unmatched"] -= amount
    items = []
    planned_income = planned_expense = matched_expense = ZERO
    for line in lines:
        annual = Decimal(line.annual_equivalent)
        income = line.kind == "income"
        if income:
            planned_income += annual
        else:
            planned_expense += annual
            matched_expense += actuals[line.id]
        target = annual * factor
        observed = actuals[line.id] if has_data and counts[line.id] else None
        variance = ((observed - target) if income else (target - observed)) if observed is not None else None
        items.append(dict(name=line.name, kind=line.kind, source=line.provenance,
            annual=money(annual), monthly=money(annual / 12), weekly=money(annual / 52),
            target=money(target) if has_data else None, actual=money(observed),
            variance=money(variance), matched_count=counts[line.id],
            utilization=round(float(observed / target * 100), 1) if observed is not None and target > 0 else None))
    unallocated = sum(unmatched.values(), ZERO)
    total_spend = matched_expense + unallocated
    annual_surplus = planned_income - planned_expense
    plan_target = planned_expense * factor
    net = observed_income - total_spend
    history = []
    if has_data:
        for m in (7,8,9,10,11,12,1,2,3,4,5,6):
            a,b = period_dates(year,m)
            if a > cutoff or b < coverage_start:
                continue
            key = a.strftime("%Y-%m")
            part = months_between(max(a,coverage_start),min(b,cutoff))
            v = monthly[key]
            history.append(dict(month=key, target=money(planned_expense*part/12),
                                actual=money(v["matched"]+v["unmatched"]),
                                matched=money(v["matched"]), unallocated=money(v["unmatched"])))
    warnings = [
        "Current workbook plan applied to the selected dates; not a historical budget. Recent rent and other changes distort earlier comparisons.",
        "Annual column G is authoritative; equivalents are recalculated. Mortgage plan may reference next calculated interest rather than contractual repayments; verify against your loan statement.",
        "Only explicitly matched transactions are allocated. A dash means no matched evidence, not zero spending. Unallocated debits remain in observed spending.",
        "Mortgage interest and internal transfers excluded to avoid double counting repayments. BNPL cash payments are separately reported because original purchases may already be counted.",
        "Savings scenarios use net income consistently; tax refund/HECS estimates are excluded from cash available. Observed surplus is not verified savings."
    ]
    if not has_data:
        warnings.append("No transaction coverage in selected period.")
    if has_data and coverage_start > start:
        warnings.append("Transaction history begins after the requested period start.")
    run = db.session.get(ImportRun, lines[0].source_run_id) if lines[0].source_run_id else None
    newest_run = ImportRun.query.filter_by(status="completed").order_by(ImportRun.id.desc()).first()
    if newest_run and run and newest_run.id != run.id:
        warnings.append("Budget is from an older successful import; check latest import warnings and source workbook.")
    base.update(status="ok", start=start.isoformat(), end=end.isoformat(),
        covered_from=coverage_start.isoformat() if has_data else None,
        covered_to=cutoff.isoformat() if has_data else None,
        source_import=run.id if run else None, warnings=warnings, lines=items, history=history,
        plan=dict(annual_income=money(planned_income), annual_expenses=money(planned_expense),
                  monthly_income=money(planned_income/12), monthly_expenses=money(planned_expense/12),
                  monthly_surplus=money(annual_surplus/12), annual_surplus=money(annual_surplus),
                  savings_rate=round(float(annual_surplus/planned_income*100),1) if planned_income else None,
                  scenarios=[dict(percent=p, monthly_target=money(planned_income*p/1200),
                                  monthly_remaining=money((annual_surplus-planned_income*p/100)/12))
                             for p in (10,15,20)]),
        actual=dict(income=money(observed_income) if has_data else None,
                    target_income=money(planned_income*factor) if has_data else None,
                    spending=money(total_spend) if has_data else None,
                    target=money(plan_target) if has_data else None,
                    variance=money(plan_target-total_spend) if has_data else None,
                    matched=money(matched_expense) if has_data else None,
                    unallocated=money(unallocated) if has_data else None,
                    other_income=money(other_income) if has_data else None,
                    bnpl=money(bnpl) if has_data else None,
                    excluded_debits=money(excluded_debits) if has_data else None,
                    other_credits=money(other_credits) if has_data else None,
                    net=money(net) if has_data else None,
                    daily_remaining=money((plan_target-total_spend)/((cutoff-coverage_start).days+1)) if has_data else None,
                    run_rate=money(total_spend/covered) if has_data else None),
        unallocated=[dict(category=k, amount=money(v)) for k,v in sorted(unmatched.items(),key=lambda x:-x[1])])
    return base
