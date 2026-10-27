"""Read-only Excel finance ingestion with source lineage and idempotent upserts."""
import hashlib
import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from app import db
from app.models import (ImportRun, SourceRecord, Transaction, Account, Category,
                        NetWorthSnapshot, AccountValuation)

YEAR_SHEET = re.compile(r"^Transactions_(\d{4})_NAB$", re.I)
ALIASES = {
    "date": {"date", "transaction date", "effective date"},
    "amount": {"amount", "transaction amount", "debit credit"},
    "account": {"account number", "account", "card number", "card"},
    "type": {"transaction type", "type"},
    "description": {"transaction details", "details", "description", "narrative"},
    "merchant": {"merchant name", "merchant", "payee"},
    "category": {"category", "expense category"},
}


def key(sheet, row, suffix=""):
    return hashlib.sha256(f"{sheet}|{row}|{suffix}".encode()).hexdigest()


def normalize_header(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def headers(ws):
    # Prefer the first row with Date and Amount present.
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12)):
        names = {field: next((i for i, cell in enumerate(row)
                              if normalize_header(cell.value) in choices), None)
                 for field, choices in ALIASES.items()}
        if names["date"] is not None and names["amount"] is not None:
            return row[0].row, names
    return None, {}


def amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Empty monetary amount")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    cleaned = str(value).strip().replace(",", "").replace("$", "").replace("A", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Malformed monetary amount") from exc


def parse_date(value, epoch=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and epoch is not None:
        return from_excel(value, epoch).date()
    if isinstance(value, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise ValueError("Invalid date")


def raw(ws, row, index):
    return row[index].value if index is not None and index < len(row) else None


def transaction_rows(wb):
    warnings = []
    records = []
    for ws in wb.worksheets:
        match = YEAR_SHEET.match(ws.title)
        if not match:
            continue
        header_row, columns = headers(ws)
        if header_row is None:
            warnings.append(f"{ws.title}: date/amount header not found")
            continue
        for row in ws.iter_rows(min_row=header_row + 1):
            raw_date = raw(ws, row, columns["date"])
            raw_amount = raw(ws, row, columns["amount"])
            if raw_date is None and raw_amount is None:
                continue
            try:
                d = parse_date(raw_date, wb.epoch)
                value = amount(raw_amount)
            except (ValueError, TypeError) as exc:
                warnings.append(f"{ws.title} row {row[0].row}: {exc}")
                continue
            info = {field: raw(ws, row, idx) for field, idx in columns.items()}
            records.append(dict(sheet=ws.title, row=row[0].row, date=d, amount=value,
                                account=str(info.get("account") or "").strip(),
                                category=str(info.get("category") or "").strip(),
                                merchant=str(info.get("merchant") or "").strip(),
                                description=str(info.get("description") or "").strip(),
                                type=str(info.get("type") or "").strip()))
    return records, warnings


# Known workbook row labels. Aggregates and property equity are NOT naive
# constituents of reconstructed net worth.
NW_ROWS = {12: "cash", 13: "cash", 14: "cash", 15: "cash",
           16: "cash", 17: "cash", 20: "property_equity",
           21: "hard_assets", 22: "hard_assets", 23: "hard_assets",
           26: "retirement", 27: "retirement", 28: "retirement",
           **{i: "investments" for i in range(31, 44)},
           **{i: "liabilities" for i in range(54, 61)}}
# Rows 18, 24, 29, 44, 46, 61 are workbook subtotals.


def snapshot_rows(wb):
    ws = wb["Net Worth Tracking"] if "Net Worth Tracking" in wb else None
    if ws is None:
        return [], ["Net Worth Tracking sheet missing"]
    results, warnings, dates = [], [], set()
    for col in range(2, ws.max_column + 1):
        cell = ws.cell(1, col)
        try:
            d = parse_date(cell.value, wb.epoch)
        except ValueError:
            continue
        if d in dates:
            warnings.append(f"Duplicate net worth date {d.isoformat()} at column {col}")
            continue
        dates.add(d)
        # In this local-first tool, future dated columns are forecast/placeholder, not actuals.
        if d > date.today():
            continue
        entries = []
        for row, category in NW_ROWS.items():
            value = ws.cell(row, col).value
            label = str(ws.cell(row, 1).value or f"Row {row}").strip()
            if value is None or (isinstance(value, str) and value.startswith("=")):
                continue
            try:
                numeric = amount(value)
            except ValueError:
                warnings.append(f"Snapshot {d}: non-numeric {label}")
                continue
            # Loyalty/rewards omitted; potential exchange/holding duplication remains explicit.
            entries.append(dict(row=row, label=label, category=category, value=numeric))
        source_total = ws.cell(2, col).value
        try:
            total = amount(source_total)
        except ValueError:
            total = None
            if source_total is not None:
                warnings.append(f"Snapshot {d}: reported total unavailable")
        if entries or total is not None:
            results.append(dict(date=d, reported=total, entries=entries, column=col))
    return sorted(results, key=lambda x: x["date"]), warnings


def budget_rows(wb):
    # Budget layouts vary. Preserve text rows and numeric input cells without assuming
    # the workbook's derived annual/monthly formula outputs are independent inputs.
    if "Budget" not in wb:
        return [], ["Budget sheet missing"]
    return [], ["Budget import requires source-specific frequency column verification; no inferred amounts imported"]


def profile_bytes(blob, filename="Financial Dashboard.xlsx"):
    digest = hashlib.sha256(blob).hexdigest()
    formula = load_workbook(io.BytesIO(blob), data_only=False, read_only=True)
    cached = load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    records, warnings = transaction_rows(cached)
    snapshots, nw_warnings = snapshot_rows(cached)
    _, budget_warnings = budget_rows(cached)
    warnings.extend(nw_warnings + budget_warnings)
    sheets = [dict(name=s.title, rows=s.max_row, columns=s.max_column) for s in cached]
    missing = [] if records else ["No valid bank transactions found"]
    if not snapshots:
        missing.append("No historical net worth snapshots found")
    warnings += missing
    return dict(sha256=digest, filename=Path(filename).name, bytes=len(blob),
                sheets=sheets, transactions=records, snapshots=snapshots,
                warnings=warnings, formula_workbook=formula)


def public_preview(profile):
    return dict(filename=profile["filename"], sha256=profile["sha256"],
                bytes=profile["bytes"], sheets=profile["sheets"],
                transactions=len(profile["transactions"]), snapshots=len(profile["snapshots"]),
                warnings=profile["warnings"][:100])


def get_or_create(model, **criteria):
    item = db.session.query(model).filter_by(**criteria).first()
    if item is None:
        item = model(**criteria)
        db.session.add(item)
        db.session.flush()
    return item


def import_bytes(blob, filename, force=False):
    profile = profile_bytes(blob, filename)
    if not profile["transactions"] and not profile["snapshots"]:
        raise ValueError("No usable financial data found")
    prior = ImportRun.query.filter_by(sha256=profile["sha256"], status="completed").first()
    if prior and not force:
        return dict(import_id=prior.id, status="unchanged", counts={"created": 0, "updated": 0})
    run = ImportRun(filename=Path(filename).name, sha256=profile["sha256"],
                    size_bytes=len(blob), warnings=profile["warnings"], counts={})
    created = updated = 0
    try:
        db.session.add(run)
        db.session.flush()
        for rec in profile["transactions"]:
            source_key = key(rec["sheet"], rec["row"])
            account = get_or_create(Account, display_name=rec["account"] or "Unknown")
            category = get_or_create(Category, name=rec["category"] or "Uncategorised")
            existing = Transaction.query.filter_by(source_key=source_key).first()
            if existing is None:
                existing = Transaction(source_key=source_key)
                db.session.add(existing)
                created += 1
            else:
                updated += 1
            typ = (rec["type"] + " " + rec["category"]).lower()
            transfer = any(t in typ for t in ("transfer", "credit card payment", "internal"))
            explicit_income = any(t in typ for t in ("salary", "wages", "income", "interest received"))
            existing.date = rec["date"]
            existing.signed_amount = rec["amount"]
            existing.account_id = account.id
            if not existing.category_override:
                existing.category_id = category.id
            existing.raw_type = rec["type"]
            existing.raw_description = rec["description"]
            existing.merchant_raw = rec["merchant"]
            existing.merchant_normalized = rec["merchant"]
            existing.transfer_flag = transfer
            existing.income_flag = explicit_income and rec["amount"] > 0
            existing.excluded_from_spending = transfer
            existing.source_run_id = run.id
            # SourceRecord has NOT NULL lineage fields: populate these before
            # adding a new record, so an autoflush cannot insert a partial row.
            lineage = SourceRecord.query.filter_by(source_key=source_key).first()
            if lineage is None:
                lineage = SourceRecord(
                    source_key=source_key,
                    source_run_id=run.id,
                    sheet=rec["sheet"],
                    row_number=rec["row"],
                    payload={},
                )
                db.session.add(lineage)
            lineage.source_run_id = run.id
            lineage.sheet = rec["sheet"]
            lineage.row_number = rec["row"]
            lineage.payload = {"date": rec["date"].isoformat(), "amount": str(rec["amount"]),
                               "category": rec["category"], "merchant": rec["merchant"]}
        for snap in profile["snapshots"]:
            obj = get_or_create(NetWorthSnapshot, as_of_date=snap["date"])
            obj.source_net_worth = snap["reported"]
            obj.source_run_id = run.id
            obj.calculated_net_worth = None
            obj.reconciliation_delta = None
            for entry in snap["entries"]:
                account = get_or_create(Account, display_name=f"NW: {entry['row']} {entry['label']}")
                # All NOT NULL fields must be set before the session autoflushes.
                # get_or_create() flushes immediately and is unsafe for valuations.
                value = AccountValuation.query.filter_by(
                    snapshot_id=obj.id, account_id=account.id
                ).first()
                if value is None:
                    value = AccountValuation(
                        snapshot_id=obj.id,
                        account_id=account.id,
                        amount_aud=entry["value"],
                        kind="liability" if entry["category"] == "liabilities" else "asset",
                        category=entry["category"],
                        source_reference=f"Net Worth Tracking!{snap['column']}:{entry['row']}",
                    )
                    db.session.add(value)
                else:
                    value.amount_aud = entry["value"]
                    value.category = entry["category"]
                    value.kind = (
                        "liability" if entry["category"] == "liabilities" else "asset"
                    )
                    value.source_reference = (
                        f"Net Worth Tracking!{snap['column']}:{entry['row']}"
                    )
        run.counts = {"created": created, "updated": updated, "snapshots": len(profile["snapshots"])}
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return dict(import_id=run.id, status="completed", counts=run.counts,
                    warnings=run.warnings)
    except Exception:
        db.session.rollback()
        raise


def import_path(path, dry_run=False, force=False):
    source = Path(path).expanduser()
    if not source.is_file() or source.suffix.lower() != ".xlsx":
        raise ValueError("Existing .xlsx file required")
    blob = source.read_bytes()
    profile = profile_bytes(blob, source.name)
    return public_preview(profile) if dry_run else import_bytes(blob, source.name, force)
