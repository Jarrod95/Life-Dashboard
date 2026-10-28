"""Persisted canonical financial records. Amounts are exact decimal strings."""
from datetime import datetime, timezone
from decimal import Decimal
from app import db


def utcnow():
    return datetime.now(timezone.utc)


class ImportRun(db.Model):
    __tablename__ = "import_runs"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(20), nullable=False, default="running")
    counts = db.Column(db.JSON, nullable=False, default=dict)
    warnings = db.Column(db.JSON, nullable=False, default=list)
    importer_version = db.Column(db.String(20), default="1")
    mapping_version = db.Column(db.String(20), default="1")


class SourceRecord(db.Model):
    __tablename__ = "source_records"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(180), unique=True, nullable=False)
    source_run_id = db.Column(db.Integer, db.ForeignKey("import_runs.id"), nullable=False)
    sheet = db.Column(db.String(120), nullable=False)
    row_number = db.Column(db.Integer, nullable=False)
    column_label = db.Column(db.String(30))
    snapshot_date = db.Column(db.Date)
    payload = db.Column(db.JSON, nullable=False)
    parse_status = db.Column(db.String(20), default="valid")


class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(160), unique=True, nullable=False)
    provider = db.Column(db.String(80))
    account_type = db.Column(db.String(40))
    parent_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    currency = db.Column(db.String(3), default="AUD")
    source_alias = db.Column(db.String(160))
    active = db.Column(db.Boolean, default=True)


class NetWorthSnapshot(db.Model):
    __tablename__ = "net_worth_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    as_of_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    source_run_id = db.Column(db.Integer, db.ForeignKey("import_runs.id"))
    source_net_worth = db.Column(db.Numeric(18, 2))
    calculated_net_worth = db.Column(db.Numeric(18, 2))
    reconciliation_delta = db.Column(db.Numeric(18, 2))
    notes = db.Column(db.Text)


class AccountValuation(db.Model):
    __tablename__ = "account_valuations"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("net_worth_snapshots.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    amount_aud = db.Column(db.Numeric(18, 2), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    category = db.Column(db.String(32), nullable=False)
    source_reference = db.Column(db.String(160))
    __table_args__ = (db.UniqueConstraint("snapshot_id", "account_id"),)


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    category_type = db.Column(db.String(20), default="expense")
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    display_order = db.Column(db.Integer, default=0)


class MerchantRule(db.Model):
    __tablename__ = "merchant_rules"
    id = db.Column(db.Integer, primary_key=True)
    priority = db.Column(db.Integer, default=0)
    match_type = db.Column(db.String(20), default="contains")
    pattern = db.Column(db.String(160), nullable=False)
    merchant = db.Column(db.String(160))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    enabled = db.Column(db.Boolean, default=True)


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(180), nullable=False, unique=True)
    date = db.Column(db.Date, nullable=False, index=True)
    signed_amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default="AUD")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    raw_type = db.Column(db.String(160))
    raw_description = db.Column(db.Text)
    merchant_raw = db.Column(db.String(200))
    merchant_normalized = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), index=True)
    transfer_flag = db.Column(db.Boolean, default=False)
    income_flag = db.Column(db.Boolean, default=False)
    excluded_from_spending = db.Column(db.Boolean, default=False)
    source_run_id = db.Column(db.Integer, db.ForeignKey("import_runs.id"))
    imported_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    category_override = db.Column(db.Boolean, default=False)


class TransactionAudit(db.Model):
    __tablename__ = "transaction_audit"
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False)
    old_category_id = db.Column(db.Integer)
    new_category_id = db.Column(db.Integer)
    changed_at = db.Column(db.DateTime(timezone=True), default=utcnow)


class BudgetLine(db.Model):
    __tablename__ = "budget_lines"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(180), unique=True, nullable=False)
    source_run_id = db.Column(db.Integer, db.ForeignKey("import_runs.id"))
    fiscal_year = db.Column(db.Integer)
    name = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(20), default="expense")
    frequency = db.Column(db.String(24))
    base_amount = db.Column(db.Numeric(18, 2))
    monthly_equivalent = db.Column(db.Numeric(18, 2))
    annual_equivalent = db.Column(db.Numeric(18, 2))
    provenance = db.Column(db.String(60), default="excel")


class Goal(db.Model):
    __tablename__ = "goals"
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(40), nullable=False)
    metric_key = db.Column(db.String(80), nullable=False)
    target = db.Column(db.Numeric(18, 3), nullable=False)
    current = db.Column(db.Numeric(18, 3))
    unit = db.Column(db.String(30))
    due_date = db.Column(db.Date)
    direction = db.Column(db.String(12), default="increase")
    status = db.Column(db.String(20), default="active")

 
class DataSourceState(db.Model):
    """Last successfully imported revision of a logical source."""
    __tablename__ = "data_source_states"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), unique=True, nullable=False)
    provider = db.Column(db.String(24), nullable=False, default="onedrive")
    drive_id = db.Column(db.String(256))
    item_id = db.Column(db.String(256))
    etag = db.Column(db.String(512))
    remote_modified_at = db.Column(db.String(64))
    selected_drive_id = db.Column(db.String(256))
    selected_item_id = db.Column(db.String(256))
    sha256 = db.Column(db.String(64))
    importer_version = db.Column(db.String(80))
    last_checked_at = db.Column(db.DateTime(timezone=True))
    last_success_at = db.Column(db.DateTime(timezone=True))
    last_error_code = db.Column(db.String(64))
    last_error_summary = db.Column(db.String(256))
    status = db.Column(db.String(32), nullable=False, default="not_synced")
    last_source_type = db.Column(db.String(24))


class SyncRun(db.Model):
    """Bounded audit of imports; contains no private workbook content."""
    __tablename__ = "sync_runs"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), nullable=False, index=True)
    started_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(32), nullable=False, default="running")
    trigger = db.Column(db.String(24), nullable=False, default="manual")
    bytes_downloaded = db.Column(db.Integer, default=0)
    records_imported = db.Column(db.Integer, default=0)
    error_code = db.Column(db.String(64))
    error_summary = db.Column(db.String(256))
