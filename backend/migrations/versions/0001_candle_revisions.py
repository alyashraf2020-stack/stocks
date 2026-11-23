"""Add the correction journal to existing and new market databases."""
from alembic import op
import sqlalchemy as sa

revision = "0001_candle_revisions"
down_revision = None


def upgrade():
    # Local startup may already have created the identical journal via SQLAlchemy.
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("egx_candle_revisions"):
        expected = {"id", "ticker", "session_date", "recorded_at", "reason", "before", "after"}
        columns = {col["name"] for col in inspector.get_columns("egx_candle_revisions")}
        if columns != expected:
            raise RuntimeError("Existing candle revision journal requires schema review")
        return
    op.create_table(
        "egx_candle_revisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("session_date", sa.String(10), nullable=False),
        sa.Column("recorded_at", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("before", sa.JSON, nullable=True),
        sa.Column("after", sa.JSON, nullable=False),
    )


def downgrade():
    raise RuntimeError("Restore a verified pre-migration backup to preserve the correction journal")
