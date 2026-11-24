"""Add owner policy and dated Sharia evidence without rewriting market records."""

import sqlalchemy as sa
from alembic import op

revision = "0002_portfolio_policy"
down_revision = "0001_candle_revisions"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("owner_risk_settings"):
        op.create_table(
            "owner_risk_settings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("policy", sa.JSON, nullable=False),
        )
    if not inspector.has_table("sharia_screening"):
        op.create_table(
            "sharia_screening",
            sa.Column("isin", sa.String(20), primary_key=True),
            sa.Column("reviewed_on", sa.Date, primary_key=True),
            sa.Column("evidence", sa.JSON, nullable=False),
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to preserve owner policy and Sharia evidence"
    )
