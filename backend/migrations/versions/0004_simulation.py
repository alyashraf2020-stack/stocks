"""Add virtual accounts, cash ledger and historical experiments."""

import sqlalchemy as sa
from alembic import op

revision = "0004_simulation"
down_revision = "0003_scanner"


def upgrade():
    bind = op.get_bind()
    if "recorded_at" not in {
        c["name"] for c in sa.inspect(bind).get_columns("sharia_screening")
    }:
        op.add_column("sharia_screening", sa.Column("recorded_at", sa.Float))
    metadata = sa.MetaData()
    sa.Table(
        "simulation_datasets",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("ticker", sa.String(20), nullable=False, index=True),
        sa.Column("imported", sa.Float, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    sa.Table(
        "paper_accounts",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created", sa.Float, nullable=False),
        sa.Column("start_capital", sa.String(28), nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False),
        sa.Column("automated", sa.Boolean, nullable=False),
        sa.Column("auto_cursor", sa.String(10)),
        sa.Column("failure", sa.String(48)),
        sa.Column("strategy", sa.String(16), nullable=False),
        sa.Column("datasets", sa.JSON, nullable=False),
        sa.Column("execution", sa.JSON, nullable=False),
        sa.Column("book", sa.JSON, nullable=False),
        sa.Column("initial_request", sa.JSON, nullable=False),
    )
    sa.Table(
        "paper_orders",
        metadata,
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_accounts.id"),
            primary_key=True,
        ),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    sa.Table(
        "paper_ledger",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("created", sa.Float, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.UniqueConstraint("account_id", "key"),
    )
    sa.Table(
        "paper_trades",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("order_id", sa.String(36), nullable=False),
        sa.Column("session", sa.String(10), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.UniqueConstraint("account_id", "order_id", "session"),
    )
    sa.Table(
        "backtest_runs",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("queued", sa.Float, nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("lease", sa.Float),
        sa.Column("token", sa.String(32)),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("progress", sa.Integer, nullable=False),
        sa.Column("error", sa.String(48)),
        sa.Column("parameters", sa.JSON, nullable=False),
    )
    sa.Table(
        "backtest_results",
        metadata,
        sa.Column(
            "id", sa.String(64), sa.ForeignKey("backtest_runs.id"), primary_key=True
        ),
        sa.Column("data", sa.JSON, nullable=False),
    )
    sa.Table(
        "backtest_trades",
        metadata,
        sa.Column(
            "result_id",
            sa.String(64),
            sa.ForeignKey("backtest_results.id"),
            primary_key=True,
        ),
        sa.Column("sequence", sa.Integer, primary_key=True),
        sa.Column("scenario", sa.String(48), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    metadata.create_all(bind, checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to preserve virtual ledger history"
    )
