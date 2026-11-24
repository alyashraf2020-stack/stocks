"""Add the SQLite scanner queue, observations and notification outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0003_scanner"
down_revision = "0002_portfolio_policy"


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    sa.Table(
        "scanner_control",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("settings", sa.JSON, nullable=False),
        sa.Column("last_broker_check", sa.Float),
    )
    sa.Table(
        "scanner_jobs",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("window", sa.String(100), unique=True, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("session", sa.String(10), nullable=False),
        sa.Column("status", sa.String(16), index=True, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("queued", sa.Float, index=True, nullable=False),
        sa.Column("due", sa.Float, nullable=False),
        sa.Column("started", sa.Float),
        sa.Column("finished", sa.Float),
        sa.Column("lease_until", sa.Float),
        sa.Column("token", sa.String(32)),
        sa.Column("error", sa.String(40)),
    )
    sa.Table(
        "scanner_heartbeats",
        metadata,
        sa.Column("worker_id", sa.String(32), primary_key=True),
        sa.Column("seen", sa.Float, index=True, nullable=False),
        sa.Column("job_id", sa.Integer),
    )
    sa.Table(
        "scanner_runs",
        metadata,
        sa.Column("job_id", sa.Integer, primary_key=True),
        sa.Column("created", sa.Float, index=True, nullable=False),
        sa.Column("summary", sa.JSON, nullable=False),
        sa.Column("results", sa.JSON, nullable=False),
    )
    sa.Table(
        "scanner_signals",
        metadata,
        sa.Column("scope", sa.String(40), primary_key=True),
        sa.Column("ticker", sa.String(20), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("updated", sa.Float, index=True, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    sa.Table(
        "scanner_notifications",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("series", sa.String(100), index=True, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("created", sa.Float, index=True, nullable=False),
        sa.Column("expires", sa.Float, nullable=False),
        sa.Column("read_at", sa.Float),
        sa.Column("acknowledged_at", sa.Float),
        sa.Column("payload", sa.JSON, nullable=False),
    )
    sa.Table(
        "scanner_notification_outbox",
        metadata,
        sa.Column("notification_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(12), index=True, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("due", sa.Float, nullable=False),
        sa.Column("token", sa.String(32)),
        sa.Column("history", sa.JSON, nullable=False),
    )
    sa.Table(
        "scanner_audit",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", sa.Float, index=True, nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("job_id", sa.Integer),
    )
    metadata.create_all(bind, checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to preserve scanner settings and history"
    )
