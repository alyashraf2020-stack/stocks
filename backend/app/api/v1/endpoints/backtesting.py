import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.api.v1.endpoints.paper_trading import checked
from app.core.database import get_db
from app.models.backtest_result import BacktestResult
from app.models.backtest_run import BacktestRun
from app.models.backtest_trade import BacktestTrade
from app.schemas.backtesting import BacktestRequest, DatasetUpload
from app.services import backtesting
from app.services.backtest_data import dataset_catalog, import_dataset, raw_inventory
from app.services.scanner_calendar import CAIRO
from app.services.scanner_repository import writer

router = APIRouter(prefix="/backtesting", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]
RunID = Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")]


def status(row):
    return {
        "id": row.id,
        "status": row.status,
        "queued": row.queued,
        "progress": row.progress,
        "attempts": row.attempts,
        "error": row.error,
        "strategies": row.parameters["request"]["strategies"],
        "start": row.parameters["request"]["start"],
        "end": row.parameters["request"]["end"],
    }


@router.get("/datasets")
def datasets(db: DB):
    return {"approved": dataset_catalog(db), "cached_inventory": raw_inventory(db)}


@router.post("/datasets", status_code=201)
def upload(request: DatasetUpload, db: DB):
    with writer(db):
        row = checked(import_dataset, db, request, datetime.now(CAIRO))
        key, checksum = row.id, row.digest
    return {"id": key, "digest": checksum}


@router.get("/runs")
def runs(db: DB):
    return [
        status(row)
        for row in db.scalars(
            select(BacktestRun).order_by(BacktestRun.queued.desc()).limit(100)
        )
    ]


@router.post("/runs", status_code=202)
def enqueue(request: BacktestRequest, db: DB):
    return {"id": checked(backtesting.enqueue, db, request, datetime.now(CAIRO))}


@router.get("/runs/{run_id}")
def result(run_id: RunID, db: DB):
    row = db.get(BacktestRun, run_id)
    if not row:
        raise HTTPException(404, "UNKNOWN_BACKTEST")
    saved = db.get(BacktestResult, run_id)
    return {**status(row), "result": saved.data if saved else None}


@router.get("/runs/{run_id}/trades")
def trades(
    run_id: RunID,
    db: DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return [
        {"scenario": row.scenario, **row.data}
        for row in db.scalars(
            select(BacktestTrade)
            .where(BacktestTrade.result_id == run_id)
            .order_by(BacktestTrade.sequence)
            .offset(offset)
            .limit(limit)
        )
    ]


@router.get("/runs/{run_id}/export.csv")
def export(run_id: RunID, db: DB):
    if not db.get(BacktestResult, run_id):
        raise HTTPException(404, "BACKTEST_RESULT_UNAVAILABLE")
    stream = io.StringIO()
    columns = (
        "scenario",
        "ticker",
        "side",
        "trade_session",
        "decision_session",
        "price",
        "shares",
        "notional",
        "fees",
        "tax",
        "slippage",
        "realized",
        "reason",
    )
    output = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    output.writeheader()
    for row in db.scalars(
        select(BacktestTrade)
        .where(BacktestTrade.result_id == run_id)
        .order_by(BacktestTrade.sequence)
    ):
        output.writerow({"scenario": row.scenario, **row.data})
    return Response(
        stream.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="egx-virtual-backtest.csv"'
        },
    )


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: RunID, db: DB):
    if not backtesting.cancel(db, run_id):
        raise HTTPException(404, "UNKNOWN_BACKTEST")
    return {"updated": True}
