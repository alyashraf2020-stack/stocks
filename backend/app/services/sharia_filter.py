from datetime import datetime

from sqlalchemy import select

from app.models.sharia_screening import ShariaScreening
from app.schemas.sharia import ScreeningEvidence
from app.services.egx_calendar import CAIRO_TZ
from app.services.sharia_screening import evaluate_screen


def status_for(db, security, today=None):
    today = today or datetime.now(CAIRO_TZ).date()
    row = (
        db.scalar(
            select(ShariaScreening)
            .where(
                ShariaScreening.isin == security.isin,
                ShariaScreening.reviewed_on <= today,
            )
            .order_by(ShariaScreening.reviewed_on.desc())
            .limit(1)
        )
        if security.isin
        else None
    )
    evidence = ScreeningEvidence.model_validate(row.evidence) if row else None
    return evaluate_screen(evidence, today)
