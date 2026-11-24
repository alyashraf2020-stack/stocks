"""Private owner controls. Job leases and publishing remain worker-only."""

import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.models.market_scan import MarketScan
from app.models.scheduled_job import ScannerAudit, ScheduledJob
from app.models.security import EGXSecurity
from app.schemas.scanner import ScannerSettings
from app.services.notification_service import CATEGORIES
from app.services.risk_policy import entry_blocks, load_policy
from app.services.scanner_broker import local_broker_state
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_health import health
from app.services.scanner_repository import (
    digest,
    enqueue,
    load_settings,
    save_settings,
    suppress_entry,
)
from app.services.sharia_filter import status_for

router = APIRouter(prefix="/scanner", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


@router.get("/settings", response_model=ScannerSettings)
def settings(db: DB):
    return load_settings(db)


@router.post("/settings", response_model=ScannerSettings)
def update_settings(data: ScannerSettings, db: DB):
    if set(data.muted_categories) - CATEGORIES:
        raise HTTPException(422, "INVALID_ALERT_CATEGORY")
    if data.enabled and data.interval_seconds:
        raise HTTPException(422, "LICENSED_INTRADAY_FEED_REQUIRED")
    updated = save_settings(db, data)
    if updated is None:
        raise HTTPException(409, "SETTINGS_CHANGED")
    return updated


@router.get("/status")
async def status(db: DB):
    now = time.time()
    result = health(db, now, calendar_at(datetime.fromtimestamp(now, UTC)))
    summary = result["last_summary"]
    if summary and summary["mode"] == "THNDR_PORTFOLIO":
        async with local_broker_state(summary["broker_sync"]) as authorized:
            if not authorized:
                result["last_summary"] = None
                result["last_success"] = None
    return result


@router.post("/run", status_code=202)
def run(db: DB):
    now = datetime.now(UTC)
    job = enqueue(db, calendar_at(now), now.timestamp(), manual=True)
    if job is None:
        raise HTTPException(422, "NO_COVERED_EOD_WINDOW_OR_FEED_REQUIRED")
    return {"job_id": job, "executable": False}


@router.get("/history")
def history(db: DB, limit: int = Query(20, ge=1, le=100)):
    jobs = db.scalars(
        select(ScheduledJob).order_by(ScheduledJob.id.desc()).limit(limit)
    )
    return [
        {
            key: getattr(row, key)
            for key in (
                "id",
                "mode",
                "session",
                "status",
                "started",
                "queued",
                "finished",
                "attempts",
                "error",
            )
        }
        for row in jobs
    ]


@router.get("/audit")
def audit(db: DB, limit: int = Query(20, ge=1, le=100)):
    events = db.scalars(
        select(ScannerAudit).order_by(ScannerAudit.id.desc()).limit(limit)
    )
    return [
        {
            "at": item.at,
            "action": item.action,
            "revision": item.revision,
            "job_id": item.job_id,
        }
        for item in events
    ]


@router.get("/results")
async def results(
    db: DB,
    job_id: int | None = None,
    offset: int = Query(0, ge=0, le=2000),
    limit: int = Query(30, ge=1, le=100),
    category: str = Query("", max_length=30),
    sector: str = Query("", max_length=100),
    rating: str = Query("", max_length=20),
    risk: str = Query("", max_length=20),
    sharia: str = Query("", max_length=20),
    freshness: str = Query("", max_length=20),
    signal: str = Query("", max_length=20),
    min_turnover: float = Query(0, ge=0, le=1e15),
):
    now = datetime.now(UTC)
    current = load_settings(db)
    if job_id:
        run_row = db.get(MarketScan, job_id)
    else:
        run_row = db.scalar(
            select(MarketScan)
            .join(ScheduledJob, ScheduledJob.id == MarketScan.job_id)
            .where(
                ScheduledJob.revision == current.revision,
            )
            .order_by(MarketScan.job_id.desc())
            .limit(1)
        )
    if not run_row:
        return {"job_id": None, "summary": None, "rows": [], "total": 0, "sectors": []}
    source = run_row.summary["mode"]
    if source == "THNDR_PORTFOLIO":
        async with local_broker_state(run_row.summary.get("broker_sync")) as authorized:
            if not authorized:
                return {
                    "job_id": run_row.job_id,
                    "summary": None,
                    "rows": [],
                    "total": 0,
                    "sectors": [],
                    "error": "THNDR_AUTHORIZATION_OR_SYNC_REQUIRED",
                }
    policy = load_policy(db)
    cal = calendar_at(now)
    policy_changed = run_row.summary.get("policy_digest") != digest(
        policy.model_dump(mode="json")
    )
    job = db.get(ScheduledJob, run_row.job_id)
    filtered = []
    sectors = set()
    for row in deepcopy(run_row.results):
        report = row.get("analysis") or {}
        if report.get("sector"):
            sectors.add(report["sector"])
        if report:
            security = db.get(EGXSecurity, row["ticker"])
            screening = (
                status_for(db, security, now.astimezone(CAIRO).date())["status"]
                if security
                else "UNVERIFIED"
            )
            blocks = entry_blocks(
                policy, screening, advanced_supported=source.endswith("_PORTFOLIO")
            )
            if policy_changed:
                blocks.append("POLICY_CHANGED")
            if (
                row["qualified"]
                and run_row.summary.get("portfolio_as_of")
                and (
                    now - datetime.fromisoformat(run_row.summary["portfolio_as_of"])
                    > timedelta(minutes=policy.max_snapshot_minutes)
                )
            ):
                blocks.append("CURRENT_SNAPSHOT")
            if (
                cal["completed_session"] != job.session
                or job.revision != current.revision
            ):
                blocks.append("HISTORICAL_SCAN")
            if cal["session_status"] == "HALTED":
                blocks.append("MARKET_HALTED")
            if (
                report.get("expires_at")
                and datetime.fromisoformat(report["expires_at"]) <= now
            ):
                blocks.append("SIGNAL_EXPIRED")
            if (
                not security
                or security.listing_status != "ACTIVE"
                or security.isin != row["observation"]["instrument_id"]
            ):
                blocks.append("INSTRUMENT_CHANGED")
            report["sharia_status"] = screening
            if blocks:
                suppress_entry(row, *blocks)
        if category and row["category"] != category:
            continue
        if any(
            value and report.get(key) != value
            for key, value in {
                "sector": sector,
                "technical_rating": rating,
                "risk": risk,
                "sharia_status": sharia,
                "freshness": freshness,
                "signal": signal,
            }.items()
        ):
            continue
        if (
            min_turnover
            and (report.get("mean_volume") or 0) * (report.get("price") or 0)
            < min_turnover
        ):
            continue
        filtered.append(row)
    return {
        "job_id": run_row.job_id,
        "summary": run_row.summary,
        "rows": filtered[offset : offset + limit],
        "total": len(filtered),
        "sectors": sorted(sectors),
    }
