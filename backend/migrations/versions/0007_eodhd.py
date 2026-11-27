"""Add isolated EODHD analytical history and UTC usage accounting."""

from alembic import op

from app.models.eodhd import EodhdCandle, EodhdConfig, EodhdSync, EodhdUsage

revision = "0007_eodhd"
down_revision = "0006_order_review"


def upgrade():
    for model in (EodhdConfig, EodhdUsage, EodhdCandle, EodhdSync):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError(
        "Restore a verified pre-migration backup to preserve EODHD state"
    )
