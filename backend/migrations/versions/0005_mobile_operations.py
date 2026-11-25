"""Persist channel delivery settings and import receipts without rewriting existing data."""

import sqlalchemy as sa
from alembic import op

revision = "0005_mobile_operations"
down_revision = "0004_simulation"


def upgrade():
    tables = sa.MetaData()
    sa.Table(
        "delivery_settings",
        tables,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("pair_hash", sa.String(64)),
        sa.Column("pair_expires", sa.Float),
        sa.Column("next_pair_check", sa.Float),
    )
    sa.Table(
        "delivery_targets",
        tables,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("channel", sa.String(12), nullable=False),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("since", sa.Float, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("last_ok", sa.Float),
    )
    sa.Table(
        "channel_deliveries",
        tables,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("notification_id", sa.String(64), nullable=False, index=True),
        sa.Column("series", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(12), nullable=False, index=True),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created", sa.Float, nullable=False),
        sa.Column("due", sa.Float, nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("token", sa.String(32)),
        sa.Column("lease", sa.Float),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error", sa.String(48)),
        sa.Column("history", sa.JSON, nullable=False),
        sa.Column("test", sa.Boolean, nullable=False),
    )
    sa.Table(
        "channel_throttle",
        tables,
        sa.Column("channel", sa.String(12), primary_key=True),
        sa.Column("until", sa.Float, nullable=False),
    )
    sa.Table(
        "worker_pulses",
        tables,
        sa.Column("role", sa.String(20), primary_key=True),
        sa.Column("seen", sa.Float, nullable=False),
    )
    sa.Table(
        "market_imports",
        tables,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fingerprint", sa.String(64), unique=True, nullable=False),
        sa.Column("dataset_id", sa.String(36), index=True),
        sa.Column("ticker", sa.String(20)),
        sa.Column("session", sa.String(10), index=True),
        sa.Column("created", sa.Float, nullable=False, index=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("report", sa.JSON, nullable=False),
    )
    tables.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to retain delivery and import history"
    )
