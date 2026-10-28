"""Server-rendered pages and same-origin versioned JSON API."""
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from flask import Blueprint, render_template, jsonify, request, current_app
from app import db
from app.models import (ImportRun, NetWorthSnapshot, Transaction, Category, TransactionAudit,
                        BudgetLine, Goal)
from app.finance import (summary, timeline, spending, transaction_query, transaction_json,
                         latest_valuations, mortgage_scenario, money, spending_categories, transaction_years, income_audit)
from app.importer import profile_bytes, public_preview, import_bytes

site = Blueprint("site", __name__)
api = Blueprint("api", __name__, url_prefix="/api/v1")


def parse_day(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD") from exc


def error(message, status=400, code="validation_error"):
    return jsonify(error={"code": code, "message": message}), status


def date_args():
    start, end = parse_day(request.args.get("from")), parse_day(request.args.get("to"))
    if start and end and start > end:
        raise ValueError("from must be on or before to")
    return start, end


@site.get("/")
def home():
    from app.body_composition import overview_data, status_data
    return render_template("dashboard.html", section="overview", title="Overview",
                           data=summary(), spending=spending(), networth=timeline(),
                           composition=overview_data(), composition_status=status_data())


@site.get("/finance")
@site.get("/finance/net-worth")
@site.get("/finance/spending")
@site.get("/finance/budget")
@site.get("/finance/mortgage")
def finance_page():
    path = request.path
    section = path.split("/")[-1] if path != "/finance" else "finance"
    return render_template("dashboard.html", section=section, title=section.replace("-", " ").title(),
                           data=summary(), spending=spending(), networth=timeline(),
                           valuations=latest_valuations(),
                           tx_count=db.session.query(Transaction).count(),
                           categories=Category.query.order_by(Category.name).all(),
                           budgets=BudgetLine.query.all(), years=transaction_years())


@site.get("/fitness")
@site.get("/health-dashboard")
@site.get("/goals")
def scaffold():
    module = request.path.strip("/")
    return render_template("scaffold.html", section=module, title=module.replace("-", " ").title())


@site.get("/settings/imports")
def imports_page():
    return render_template("imports.html", section="imports", title="Data & imports",
                           runs=ImportRun.query.order_by(ImportRun.id.desc()).limit(20).all(),
                           configured=bool(current_app.config.get("SOURCE_WORKBOOK")))


@api.errorhandler(ValueError)
def value_error(exc):
    return error(str(exc))


@api.get("/overview")
def overview_api():
    from app.body_composition import overview_data, status_data
    from app.life_summary import other_sources
    return jsonify(data={"finance": summary(), "body_composition": overview_data(),
                         "other_sources": other_sources()}, meta={"body_composition": status_data()})


@api.get("/finance/summary")
def summary_api():
    return jsonify(summary(parse_day(request.args.get("as_of"))))


@api.get("/finance/net-worth")
def networth_api():
    start, end = date_args()
    return jsonify(data=timeline(start, end), valuations=latest_valuations())


@api.get("/finance/net-worth/<int:snapshot_id>")
def snapshot_api(snapshot_id):
    snapshot = db.session.get(NetWorthSnapshot, snapshot_id)
    if snapshot is None:
        return error("Snapshot not found", 404, "not_found")
    from app.finance import snapshot_json
    from app.models import AccountValuation, Account
    valuations = db.session.query(AccountValuation, Account).join(Account).filter(
        AccountValuation.snapshot_id == snapshot_id).all()
    return jsonify(snapshot=snapshot_json(snapshot),
                   valuations=[dict(account=a.display_name, amount=money(v.amount_aud),
                                    kind=v.kind, category=v.category) for v, a in valuations])


@api.get("/finance/transactions")
def transactions_api():
    start, end = spending_dates() if request.args.get("year") else date_args()
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("page_size", "50"))
        category = int(request.args["category"]) if request.args.get("category") else None
        account = int(request.args["account"]) if request.args.get("account") else None
    except ValueError:
        return error("Invalid pagination, category or account")
    if page < 1 or not 1 <= size <= 200:
        return error("page must be >= 1; page_size must be 1–200")
    query = transaction_query(start, end, category, request.args.get("merchant"), account,
                              request.args.get("include_transfers") == "true",
                              request.args.get("search"))
    sort = request.args.get("sort", "date")
    if sort not in {"date", "amount", "merchant"}:
        return error("Unsupported sort field")
    column = {"date": Transaction.date, "amount": Transaction.signed_amount,
              "merchant": Transaction.merchant_normalized}[sort]
    query = query.order_by(column.asc() if request.args.get("order") == "asc" else column.desc(),
                           Transaction.id.desc())
    items = query.paginate(page=page, per_page=size, error_out=False)
    return jsonify(data=[transaction_json(t) for t in items.items], page=page, page_size=size,
                   total=items.total, pages=items.pages)


@api.patch("/finance/transactions/<int:transaction_id>/category")
def category_update_api(transaction_id):
    transaction = db.session.get(Transaction, transaction_id)
    if transaction is None:
        return error("Transaction not found", 404, "not_found")
    body = request.get_json(silent=True) or {}
    try:
        cid = int(body["category_id"])
    except (KeyError, ValueError, TypeError):
        return error("category_id must be an integer")
    category = db.session.get(Category, cid)
    if category is None:
        return error("Category not found", 404, "not_found")
    db.session.add(TransactionAudit(transaction_id=transaction.id,
                                    old_category_id=transaction.category_id, new_category_id=cid))
    transaction.category_id = cid
    transaction.category_override = True
    db.session.commit()
    return jsonify(data=transaction_json(transaction))


@api.get("/finance/spending")
def spending_api():
    start, end = spending_dates() if request.args.get("year") else date_args()
    grouping = request.args.get("group_by", "month")
    if grouping not in {"month", "year", "category", "merchant"}:
        return error("group_by must be month, year, category or merchant")
    return jsonify(data=spending(start, end, grouping))


@api.get("/finance/spending/categories")
def spending_categories_api():
    start, end = spending_dates() if request.args.get("year") else date_args()
    return jsonify(data=spending_categories(start, end),
                   from_date=start.isoformat() if start else None,
                   to_date=end.isoformat() if end else None)


@api.get("/finance/spending/years")
def spending_years_api():
    return jsonify(data=transaction_years())




def spending_period():
    from app.finance_insights import period
    return period(request.args.get("year"), request.args.get("month"))


def spending_dates():
    """Explicit from/to dates take precedence over year/month for legacy consumers."""
    if request.args.get("from") or request.args.get("to"):
        return date_args()
    p = spending_period()
    return p["start"], p["end"]


@api.get("/finance/spending/periods")
def insights_periods_api():
    from app.finance_insights import period, metadata
    p = period()
    from app.models import Transaction
    rows = db.session.query(Transaction.date).all()
    available = {}
    for (day,) in rows:
        available.setdefault(str(day.year), set()).add(day.month)
    return jsonify(data={"years": p["years"], "months_by_year": {y: sorted(v) for y,v in available.items()},
                         "default": metadata(p)})


@api.get("/finance/spending/summary")
def insights_summary_api():
    from app.finance_insights import public_summary
    return jsonify(data=public_summary(spending_period()))


@api.get("/finance/spending/merchants")
def insights_merchants_api():
    from app.finance_insights import summarize
    s = summarize(spending_period())
    entries = s["merchants"]
    sort = request.args.get("sort", "spend_desc")
    if sort not in ("spend_desc", "spend_asc", "merchant", "count_desc"):
        return error("Invalid merchant sort")
    if sort == "spend_asc":
        entries = list(reversed(entries))
    elif sort == "merchant":
        entries = sorted(entries, key=lambda item:item["merchant"])
    elif sort == "count_desc":
        entries = sorted(entries, key=lambda item:-item["transactions"])
    return jsonify(data=entries[:500], total=len(entries), period=s["period"])


@api.get("/finance/spending/insights")
def insights_opportunities_api():
    from app.finance_insights import summarize, opportunities
    s = summarize(spending_period())
    return jsonify(data=opportunities(s), period=s["period"], warnings=s["warnings"])


@api.get("/finance/spending/recurring")
def insights_recurring_api():
    from app.finance_insights import summarize, recurring
    s = summarize(spending_period())
    return jsonify(data=recurring(s), period=s["period"], warnings=s["warnings"])


@api.get("/finance/spending/cashflow")
def insights_cashflow_api():
    from app.finance_insights import summarize
    s = summarize(spending_period())
    return jsonify(data=s["cashflow"], period=s["period"])

@api.get("/finance/income-audit")
def income_audit_api():
    """Local-only aggregate source/DB reconciliation; no account details or narratives."""
    return jsonify(data=income_audit())


@api.get("/finance/budget")
def budget_api():
    year = request.args.get("fiscal_year")
    try:
        year = int(year) if year else None
    except ValueError:
        return error("Invalid fiscal_year")
    query = BudgetLine.query
    if year:
        query = query.filter_by(fiscal_year=year)
    return jsonify(data=[dict(name=b.name, frequency=b.frequency, kind=b.kind,
                              fiscal_year=b.fiscal_year, base=money(b.base_amount),
                              monthly=money(b.monthly_equivalent),
                              annual=money(b.annual_equivalent)) for b in query.all()],
                   warning="Source budget frequency mapping is pending workbook validation")


@api.get("/finance/mortgage")
def mortgage_api():
    from app.finance import mortgage_tracking
    return jsonify(data=mortgage_tracking())


@api.post("/finance/mortgage/scenarios")
def scenario_api():
    payload = request.get_json(silent=True) or {}
    try:
        result = mortgage_scenario(
            principal=Decimal(str(payload["principal"])),
            annual_rate=Decimal(str(payload["annual_rate"])),
            offset=Decimal(str(payload.get("offset", 0))),
            payment=Decimal(str(payload["monthly_payment"])),
            extra=Decimal(str(payload.get("extra_monthly_payment", 0))),
            monthly_topup=Decimal(str(payload.get("monthly_offset_topup", 0))))
    except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
        return error(str(exc))
    return jsonify(data=result, assumptions={
        "rate": "nominal annual rate divided by 12",
        "payment": "end of month", "offset": "reduces interest-bearing balance, not principal",
        "horizon_months": 600})


@api.get("/imports")
def imports_api():
    return jsonify(data=[dict(id=r.id, filename=r.filename, sha256=r.sha256, status=r.status,
                              counts=r.counts, warnings=r.warnings,
                              completed_at=r.completed_at.isoformat() if r.completed_at else None)
                         for r in ImportRun.query.order_by(ImportRun.id.desc()).limit(100)])


def load_upload():
    uploaded = request.files.get("file")
    if uploaded:
        if Path(uploaded.filename or "").suffix.lower() != ".xlsx":
            raise ValueError("Only .xlsx workbooks are supported")
        raw = uploaded.read()
        if not raw:
            raise ValueError("Empty workbook")
        return raw, Path(uploaded.filename).name
    # Graph mode must not silently fall back to a stale Windows workbook.
    if current_app.config.get("LIFE_DATA_SOURCE") == "onedrive":
        raise ValueError("Use Data Sources > Sync now for the configured OneDrive workbook")
    # No arbitrary path accepted from the browser.
    source = current_app.config.get("SOURCE_WORKBOOK")
    if not source or not Path(source).is_file():
        raise ValueError("Upload a workbook or configure LIFE_FINANCE_XLSX_PATH")
    return Path(source).read_bytes(), Path(source).name


@api.post("/imports/finance/preview")
def preview_api():
    try:
        raw, name = load_upload()
        return jsonify(data=public_preview(profile_bytes(raw, name)))
    except (ValueError, OSError, Exception) as exc:
        # Avoid embedding sensitive workbook data in exception messages.
        return error("Unable to parse workbook: " + type(exc).__name__)


@api.post("/imports/finance")
def import_api():
    try:
        raw, name = load_upload()
        result = import_bytes(raw, name, force=request.form.get("force") == "true")
        return jsonify(data=result)
    except Exception as exc:
        return error("Import failed: " + type(exc).__name__)


@api.get("/imports/<int:run_id>")
def import_status_api(run_id):
    run = db.session.get(ImportRun, run_id)
    if run is None:
        return error("Import not found", 404, "not_found")
    return jsonify(data=dict(id=run.id, status=run.status, counts=run.counts,
                             warnings=run.warnings, sha256=run.sha256))


@api.get("/fitness/summary")
def fitness_api():
    return jsonify(status="not_configured", data=None)


@api.get("/health/summary")
def health_api():
    return jsonify(status="not_configured", data=None)


@api.get("/goals")
def goals_api():
    return jsonify(data=[dict(id=x.id, module=x.module, metric=x.metric_key,
                              target=str(x.target), current=str(x.current) if x.current else None,
                              unit=x.unit, status=x.status) for x in Goal.query.all()])
