from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.models.security import EGXSecurity
from app.models.sharia_screening import ShariaScreening
from app.schemas.sharia import INDEX_URL, METHOD, METHOD_URL, ScreeningEvidence
from app.services.egx_calendar import CAIRO_TZ
from app.services.risk_policy import load_policy
from app.services.sharia_filter import status_for

router = APIRouter(prefix="/sharia", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


def security_for(db, ticker):
    security = db.get(EGXSecurity, ticker.upper())
    if not security:
        raise HTTPException(404, "UNKNOWN_SYMBOL")
    return security


@router.get("")
def overview(db: DB):
    return {
        "method": METHOD,
        "method_url": METHOD_URL,
        "index_url": INDEX_URL,
        "islamic_mode": load_policy(db).islamic_mode,
        "items": [
            {
                "ticker": s.ticker,
                "company": s.arabic_name,
                "sector": s.sector,
                **status_for(db, s),
            }
            for s in db.scalars(select(EGXSecurity).order_by(EGXSecurity.ticker))
        ],
    }


@router.get("/{ticker}")
def screening(ticker: str, db: DB):
    security = security_for(db, ticker)
    return {
        "ticker": security.ticker,
        "company": security.arabic_name,
        **status_for(db, security),
    }


@router.post("/{ticker}")
def record_evidence(ticker: str, evidence: ScreeningEvidence, db: DB):
    security = security_for(db, ticker)
    if not security.isin or evidence.reviewed_on > datetime.now(CAIRO_TZ).date():
        raise HTTPException(422, "VERIFIED_ISIN_AND_REVIEW_DATE_REQUIRED")
    key = (security.isin, evidence.reviewed_on)
    payload = evidence.model_dump(mode="json")
    row = db.get(ShariaScreening, key)
    if row is not None and row.evidence != payload:
        raise HTTPException(409, "REVIEW_DATE_ALREADY_RECORDED")
    if row is None:
        db.add(ShariaScreening(isin=key[0], reviewed_on=key[1], evidence=payload))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.get(ShariaScreening, key)
            if not existing or existing.evidence != payload:
                raise HTTPException(409, "REVIEW_DATE_ALREADY_RECORDED") from None
    return {
        "ticker": security.ticker,
        "company": security.arabic_name,
        **status_for(db, security),
    }
