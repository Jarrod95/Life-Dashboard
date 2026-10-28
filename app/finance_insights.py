"""Read-only, explainable spending analytics. Monetary arithmetic uses Decimal."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import re

from app.models import Category, Transaction
from app.finance import effective_income, money

ZERO = Decimal("0")
BNPL = ("afterpay", "zip pay", "zippay", "zipmoney", "zip money")
TRANSFER = ("transfer", "offset", "savings transfer")
PROPERTY = ("strata", "body corporate", "property management", "mortgage", "land tax", "council rates")
REPAYMENT = ("loan repayment", "credit card payment", "repayment")
ESSENTIAL = ("grocer", "supermarket", "woolworths", "coles", "aldi", "pharmacy", "medical", "electricity", "water", "insurance", "fuel", "transport")
DISCRETIONARY = ("restaurant", "takeaway", "cafe", "coffee", "dining", "entertainment", "clothing", "shopping", "subscription", "streaming", "storage", "delivery", "uber eats")
CATEGORY_ALIASES = {"personal care": "Personal Care", "take away": "Takeaway", "takeaway": "Takeaway"}


def period(year=None, month=None, today=None):
    """Resolve an inclusive calendar window, defaulting to latest transaction year."""
    today = today or date.today()
    newest = Transaction.query.order_by(Transaction.date.desc()).first()
    available = sorted({t.date.year for t in Transaction.query.with_entities(Transaction.date)}, reverse=True)
    if year in (None, "", "all"):
        year = newest.date.year if newest else today.year
    try:
        year = int(year)
        month = None if month in (None, "", "all") else int(month)
    except (TypeError, ValueError) as exc:
        raise ValueError("year and month must be integers") from exc
    if not 1900 <= year <= 2100 or (month is not None and not 1 <= month <= 12):
        raise ValueError("Invalid calendar year or month")
    start = date(year, month or 1, 1)
    last = date(year, month or 12, monthrange(year, month or 12)[1])
    latest = Transaction.query.filter(Transaction.date >= start, Transaction.date <= last).order_by(Transaction.date.desc()).first()
    label = start.strftime("%B %Y") if month else str(year) + " · All months"
    return dict(year=year, month=month, start=start, end=last, label=label,
                latest=latest.date if latest else None, today=today, years=available,
                is_partial_period=start <= today < last)


def metadata(p):
    comparison_end = p["start"] - timedelta(days=1)
    if p["month"]:
        comparison_start = date(comparison_end.year, comparison_end.month, 1)
    else:
        comparison_start = date(comparison_end.year, 1, 1)
    return dict(start=p["start"].isoformat(), end=p["end"].isoformat(),
                label=p["label"], year=p["year"], month=p["month"],
                last_transaction_date=p["latest"].isoformat() if p["latest"] else None,
                is_partial_period=p["is_partial_period"],
                comparison_interval=dict(start=comparison_start.isoformat(), end=comparison_end.isoformat()))


def merchant_name(t):
    raw = (t.merchant_normalized or t.merchant_raw or t.raw_description or "Unknown").strip()
    raw = re.sub(r"\s+", " ", raw)
    raw = re.sub(r"(?i)^(?:pos |visa purchase |eftpos |sq \*|paypal \*)", "", raw).strip()
    return raw[:100].casefold() or "unknown"


def purpose(t, name):
    if effective_income(t):
        return "income"
    if t.transfer_flag or t.excluded_from_spending:
        return "transfer"
    cat = name.casefold()
    narrative = " ".join((t.raw_description or "", t.merchant_normalized or "", cat)).casefold()
    if any(x in narrative for x in BNPL):
        return "bnpl_payment"
    if any(x in cat for x in PROPERTY) or ("investment" in cat and "property" in cat):
        return "investment_property"
    if any(x in cat for x in REPAYMENT):
        return "debt_repayment"
    if t.signed_amount > 0:
        return "refund"
    if any(x in cat for x in DISCRETIONARY):
        return "discretionary"
    if any(x in cat for x in ESSENTIAL):
        return "essential"
    return "unknown"


def records(p):
    categories = {c.id: CATEGORY_ALIASES.get(c.name.casefold(), c.name.strip().title()) for c in Category.query.all()}
    rows = Transaction.query.filter(Transaction.date >= p["start"], Transaction.date <= p["end"]).order_by(Transaction.date).all()
    result = []
    for t in rows:
        label = categories.get(t.category_id, "Uncategorised")
        kind = purpose(t, label)
        result.append(dict(id=t.id, date=t.date, amount=Decimal(t.signed_amount),
                           merchant=merchant_name(t), category=label, purpose=kind))
    return result


def eligible(row):
    return row["purpose"] in ("discretionary", "essential", "unknown", "refund")


def summarize(p):
    rows = records(p)
    consumed = [x for x in rows if eligible(x)]
    spend = sum((-x["amount"] for x in consumed), ZERO)
    discretionary = sum((-x["amount"] for x in rows if x["purpose"] == "discretionary"), ZERO)
    counts = defaultdict(int)
    totals = defaultdict(lambda: ZERO)
    by_month = defaultdict(lambda: {"income": ZERO, "spending": ZERO})
    merchants = {}
    monthly_category = defaultdict(lambda: defaultdict(lambda: ZERO))
    for x in rows:
        counts[x["purpose"]] += 1
        if x["purpose"] == "income":
            by_month[x["date"].strftime("%Y-%m")]["income"] += x["amount"]
        if eligible(x):
            amount = -x["amount"]
            totals[x["category"]] += amount
            by_month[x["date"].strftime("%Y-%m")]["spending"] += amount
            monthly_category[x["category"]][x["date"].strftime("%Y-%m")] += amount
            m = merchants.setdefault(x["merchant"], dict(merchant=x["merchant"], spend=ZERO,
                                      count=0, categories=set(), ids=[], dates=[], amounts=[]))
            m["spend"] += amount
            m["count"] += 1
            m["categories"].add(x["category"])
            m["ids"].append(x["id"])
            m["dates"].append(x["date"])
            m["amounts"].append(amount)
    merchant_data = []
    for m in merchants.values():
        merchant_data.append(dict(merchant=m["merchant"], spend_aud=money(m["spend"]),
                     transactions=m["count"], average_aud=money(m["spend"] / m["count"]),
                     share_pct=round(float(m["spend"] / spend * 100), 1) if spend > 0 else None,
                     categories=sorted(m["categories"]), transaction_ids=m["ids"]))
    merchant_data.sort(key=lambda x: (-Decimal(x["spend_aud"]), x["merchant"]))
    warnings = []
    if counts["unknown"]:
        warnings.append(f'{counts["unknown"]} unclassified transactions; insights are provisional.')
    if counts["bnpl_payment"]:
        warnings.append(f'{counts["bnpl_payment"]} BNPL payments need reconciliation against original purchases; cash debits are not included in consumption totals.')
    if counts["refund"]:
        warnings.append(f'{counts["refund"]} unmatched credits treated as refunds; category assignment should be reviewed.')
    distinct_months = len({x["date"].strftime("%Y-%m") for x in rows})
    if distinct_months < (1 if p["month"] else 12) and rows:
        warnings.append("Transaction history does not cover every month in the selected period.")
    categories_data = [dict(category=k, spending=money(v)) for k,v in sorted(totals.items(), key=lambda item: -item[1])]
    return dict(period=metadata(p), total_consumption_aud=money(spend),
                discretionary_aud=money(discretionary), transactions=len(consumed),
                average_transaction_aud=money(spend / len(consumed)) if consumed else "0.00",
                average_month_aud=money(spend / max(1, distinct_months)),
                cash_debits_aud=money(sum((-x["amount"] for x in rows if x["amount"] < 0), ZERO)),
                warnings=warnings, counts=dict(counts), categories=categories_data,
                merchants=merchant_data, rows=rows, monthly_category=monthly_category,
                cashflow=[dict(label=k, income=money(v["income"]), spending=money(v["spending"]),
                               net=money(v["income"]-v["spending"])) for k,v in sorted(by_month.items())])


def recurring(summary):
    found = []
    lookup = defaultdict(list)
    for row in summary["rows"]:
        if row["purpose"] == "discretionary" and row["amount"] < 0:
            lookup[row["merchant"]].append(row)
    for merchant, items in lookup.items():
        if len(items) < 3:
            continue
        items.sort(key=lambda x:x["date"])
        gaps = [(b["date"]-a["date"]).days for a,b in zip(items,items[1:])]
        mean = sum(gaps)/len(gaps)
        cadence = next((name for name,days,tolerance in [("weekly",7,2),("fortnightly",14,3),("monthly",30,3),("quarterly",91,7)] if all(abs(g-days)<=tolerance for g in gaps)), None)
        if not cadence:
            continue
        amounts = [-x["amount"] for x in items]
        typical = sum(amounts,ZERO)/len(amounts)
        if typical <= 0 or any(abs(a-typical) > max(Decimal("2"),typical*Decimal(".25")) for a in amounts):
            continue
        multiplier = {"weekly":Decimal(52)/12,"fortnightly":Decimal(26)/12,"monthly":Decimal(1),"quarterly":Decimal(1)/3}[cadence]
        found.append(dict(merchant=merchant, cadence=cadence, occurrences=len(items),
                          last_amount_aud=money(amounts[-1]),
                          next_expected_date=(items[-1]["date"]+timedelta(days=round(mean))).isoformat(),
                          monthly_equivalent_aud=money(typical*multiplier),
                          annual_equivalent_aud=money(typical*multiplier*12),
                          confidence="medium", transaction_ids=[x["id"] for x in items],
                          rationale=f'{len(items)} transactions approximately {round(mean)} days apart; estimated, not guaranteed.'))
    return sorted(found,key=lambda x:-Decimal(x["monthly_equivalent_aud"]))


def opportunities(summary):
    suggestions = []
    grouped = defaultdict(list)
    for row in summary["rows"]:
        if row["purpose"] == "discretionary":
            grouped[row["category"]].append(row)
    for category,items in grouped.items():
        value = sum((-x["amount"] for x in items),ZERO)
        if value <= 0 or len(items) < 2:
            continue
        reduction = Decimal("0.20")
        suggestions.append(dict(category=category, amount_aud=money(value), transactions=len(items),
            suggested_reduction_pct=20, potential_period_saving_aud=money(value*reduction),
            rationale=f'{len(items)} discretionary transactions in the selected period; consider a 20% reduction.',
            confidence="medium" if summary["period"]["is_partial_period"] else "high",
            transaction_ids=[x["id"] for x in items]))
    return sorted(suggestions,key=lambda x:-Decimal(x["potential_period_saving_aud"]))


def public_summary(p):
    s = summarize(p)
    return {k:v for k,v in s.items() if k not in ("rows","monthly_category","merchants","categories","cashflow")}
