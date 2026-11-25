from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.models.market_import import MarketImport
from app.schemas.market_import import ImportFile
from app.services.market_import import inspect_bundle, persist, readiness
from app.services.scanner_calendar import CAIRO

router = APIRouter(prefix="/data", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


@router.get("")
def summary(db: DB):
    return readiness(db, datetime.now(CAIRO))


@router.get("/history")
def history(db: DB):
    rows = db.scalars(select(MarketImport).order_by(MarketImport.id.desc()).limit(60))
    return [
        {
            "id": row.id,
            "dataset_id": row.dataset_id,
            "channel": row.channel,
            "status": row.status,
            "created": row.created,
            "report": row.report,
        }
        for row in rows
    ]


@router.post("/preview")
def preview(request: ImportFile, db: DB):
    return inspect_bundle(db, request, datetime.now(CAIRO))[1]


@router.post("/import")
def upload(request: ImportFile, db: DB):
    return persist(db, request, datetime.now(CAIRO), "MANUAL")


@router.get("/template.csv")
def template():
    return Response(
        "day,available_at,open,high,low,close,volume,tick,lower_limit,upper_limit,opening_bid,opening_ask\n",
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="egx-eod-template.csv"',
            "Cache-Control": "private, no-store",
        },
    )
