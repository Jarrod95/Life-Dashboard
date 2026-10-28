"""Add Graph source/sync audit metadata without disturbing canonical imports.

Revision ID: 001_graph_source_sync
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "001_graph_source_sync"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("data_source_states"):
        op.create_table(
            "data_source_states",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("source_key", sa.String(64), nullable=False, unique=True),
            sa.Column("provider", sa.String(24), nullable=False),
            sa.Column("drive_id", sa.String(256)),
            sa.Column("item_id", sa.String(256)),
            sa.Column("etag", sa.String(512)),
            sa.Column("remote_modified_at", sa.String(64)),
            sa.Column("selected_drive_id", sa.String(256)),
            sa.Column("selected_item_id", sa.String(256)),
            sa.Column("sha256", sa.String(64)),
            sa.Column("importer_version", sa.String(80)),
            sa.Column("last_checked_at", sa.DateTime(timezone=True)),
            sa.Column("last_success_at", sa.DateTime(timezone=True)),
            sa.Column("last_error_code", sa.String(64)),
            sa.Column("last_error_summary", sa.String(256)),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("last_source_type", sa.String(24)),
        )
    if not inspector.has_table("sync_runs"):
        op.create_table(
            "sync_runs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("source_key", sa.String(64), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("trigger", sa.String(24), nullable=False),
            sa.Column("bytes_downloaded", sa.Integer),
            sa.Column("records_imported", sa.Integer),
            sa.Column("error_code", sa.String(64)),
            sa.Column("error_summary", sa.String(256)),
        )
    index_names = {i["name"] for i in sa.inspect(conn).get_indexes("sync_runs")}
    if "ix_sync_runs_source_key" not in index_names:
        op.create_index("ix_sync_runs_source_key", "sync_runs", ["source_key"])


def downgrade():
    # Intentional no-op: never delete audit history or existing analytics by accident.
    pass
