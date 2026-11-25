"""Persist immutable review drafts and single-use local approval records."""

import sqlalchemy as sa
from alembic import op

revision = "0006_order_review"
down_revision = "0005_mobile_operations"


def upgrade():
    bind = op.get_bind()
    if "revision" not in {
        col["name"] for col in sa.inspect(bind).get_columns("owner_risk_settings")
    }:
        op.add_column(
            "owner_risk_settings",
            sa.Column("revision", sa.Integer, server_default="0", nullable=False),
        )
    metadata = sa.MetaData()
    sa.Table(
        "trading_control",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("settings", sa.JSON, nullable=False),
    )
    sa.Table(
        "order_proposals",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_key", sa.String(36), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), index=True, nullable=False),
        sa.Column("active_intent", sa.String(64), unique=True),
        sa.Column("ticker", sa.String(20), index=True, nullable=False),
        sa.Column("state", sa.String(30), index=True, nullable=False),
        sa.Column("parent_id", sa.String(36)),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created", sa.Float, index=True, nullable=False),
        sa.Column("expires", sa.Float, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
    )
    sa.Table(
        "order_events",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("order_proposals.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("created", sa.Float, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
    )
    sa.Table(
        "order_review_challenges",
        metadata,
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("order_proposals.id"),
            primary_key=True,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("binding", sa.String(64), nullable=False),
        sa.Column("expires", sa.Float, nullable=False),
        sa.Column("created", sa.Float, nullable=False),
    )
    sa.Table(
        "order_approvals",
        metadata,
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("order_proposals.id"),
            primary_key=True,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("challenge_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("policy", sa.String(64), nullable=False),
        sa.Column("created", sa.Float, nullable=False),
    )
    metadata.create_all(bind, checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to preserve proposal audit records"
    )
