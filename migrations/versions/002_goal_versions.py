"""Add goal revision metadata."""
from alembic import op
import sqlalchemy as sa

revision = "002_goal_versions"
down_revision = "001_graph_source_sync"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("goal_versions"):
        op.create_table("goal_versions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("goal_id", sa.Integer, sa.ForeignKey("goals.id"), nullable=False, unique=True),
            sa.Column("created_on", sa.Date, nullable=False),
            sa.Column("baseline", sa.Float),
            sa.Column("baseline_date", sa.Date),
            sa.Column("settings", sa.JSON, nullable=False),
            sa.Column("initial_forecast", sa.JSON),
            sa.Column("closed_on", sa.Date),
            sa.Column("outcome", sa.JSON))


def downgrade():
    # Preserve personal history.
    pass
