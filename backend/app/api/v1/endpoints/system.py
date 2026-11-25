from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.ai_trading import status as ai_status
from app.api.v1.endpoints.integrations import owner
from app.api.v1.endpoints.integrations import status as thndr_status
from app.core.database import get_db
from app.models.backtest_run import BacktestRun, SimulationDataset
from app.models.candle import EGXCandle
from app.models.delivery import DeliveryTarget, WorkerPulse
from app.models.market_import import MarketImport
from app.models.market_scan import MarketScan
from app.models.notification import Notification
from app.models.paper_account import PaperAccount
from app.models.scheduled_job import ScheduledJob
from app.schemas.market_import import ImportEnvironment
from app.schemas.paper_trading import Book
from app.services.notification_delivery import configuration, env, prefs, recent_status
from app.services.paper_portfolio import valuation
from app.services.risk_policy import load_policy
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_health import health

router = APIRouter(prefix="/system", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]
SCHEMA = "0006_order_review"


@router.get("")
async def system(db: DB):
    now = datetime.now(CAIRO)
    clock = now.timestamp()
    market = calendar_at(now)
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"fastapi": "RUNNING", "database": "UNAVAILABLE", "migration": None}
    try:
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        db.rollback()
        version = None
    if version != SCHEMA:
        return {
            "fastapi": "RUNNING",
            "database": "CONNECTED",
            "migration": {"current": version, "expected": SCHEMA, "ready": False},
        }
    scanner = health(db, clock, market)
    configured_import = ImportEnvironment().EOD_IMPORT_ENABLED
    pulses = {}
    for role, age, configured in (
        ("paper", 60, True),
        ("backtest", 25, True),
        ("notifications", 40, True),
        (
            "import",
            ImportEnvironment().EOD_IMPORT_INTERVAL_SECONDS + 60,
            configured_import,
        ),
    ):
        pulse = db.get(WorkerPulse, role)
        pulses[role] = {
            "running": bool(pulse and 0 <= clock - pulse.seen <= age),
            "seen": pulse.seen if pulse else None,
            "configured": configured,
        }
    pulses["scanner"] = {
        "running": scanner["worker_online"],
        "seen": scanner["last_heartbeat"],
        "configured": scanner["enabled"],
    }
    policy = load_policy(db)
    settings = prefs(db)
    status = configuration(env())
    channels = recent_status(db)
    targets = list(
        db.scalars(select(DeliveryTarget).where(DeliveryTarget.active.is_(True)))
    )
    for channel, flag in (("TELEGRAM", "telegram"), ("PUSH", "push")):
        linked = [item for item in targets if item.channel == channel]
        channels[channel].update(
            {
                "configured": status[channel],
                "enabled": getattr(settings, flag),
                "destinations": len(linked),
                "last_ok": max((item.last_ok or 0 for item in linked), default=0)
                or None,
            }
        )
    latest_ingest = db.scalar(
        select(MarketImport)
        .where(MarketImport.status.in_(["APPROVED", "APPROVED_PARTIAL"]))
        .order_by(MarketImport.id.desc())
        .limit(1)
    )
    raw_tickers = db.scalar(select(func.count(func.distinct(EGXCandle.ticker))))
    approved = db.scalar(
        select(func.count())
        .select_from(SimulationDataset)
        .where(SimulationDataset.data["kind"].as_string() == "EQUITY")
    )
    session_day = market["completed_session"]
    current_raw = (
        db.scalar(
            select(func.count(func.distinct(EGXCandle.ticker))).where(
                EGXCandle.session_date == session_day,
                EGXCandle.validation_status == "VALID",
            )
        )
        if session_day
        else 0
    )
    latest_run = (
        db.scalar(
            select(MarketScan)
            .where(
                MarketScan.summary["session"].as_string() == session_day,
                MarketScan.summary["mode"].as_string().in_(["MARKET", "WATCHLIST"]),
            )
            .order_by(MarketScan.job_id.desc())
            .limit(1)
        )
        if session_day
        else None
    )
    entry = []
    review = []
    if latest_run:
        for row in latest_run.results:
            report = row.get("analysis")
            if not report:
                continue
            category = row["category"]
            if category not in {
                "BUY_REVIEW",
                "ENTRY_WATCH",
                "BREAKOUT",
                "RISK_BLOCKED",
                "SHARIA_BLOCKED",
                "HOLDING_REVIEW",
            }:
                continue
            row_view = {
                "ticker": row["ticker"],
                "category": category,
                "sharia": report.get("sharia_status"),
            }
            if category in {"BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT"}:
                from types import SimpleNamespace

                from app.services.notification_delivery import opportunity_current

                instrument = (row.get("observation") or {}).get("instrument_id")
                candidate = SimpleNamespace(
                    severity="OPPORTUNITY",
                    category=category,
                    payload={
                        "_signal_expires": report.get("expires_at"),
                        "_ref_session": report.get("reference_session"),
                        "ticker": row["ticker"],
                        "_instrument": instrument,
                        "freshness": report.get("freshness"),
                    },
                )
                if opportunity_current(db, candidate, clock):
                    entry.append(row_view)
                else:
                    review.append({**row_view, "category": "RECHECK_REQUIRED"})
            else:
                review.append(row_view)
    virtual = []
    for account in db.scalars(
        select(PaperAccount)
        .where(PaperAccount.archived.is_(False))
        .order_by(PaperAccount.created.desc())
        .limit(3)
    ):
        book = Book.model_validate(account.book)
        equity = valuation(book)[0]
        virtual.append(
            {
                "name": account.name,
                "equity": equity,
                "realized": book.realized,
                "session": book.cursor,
            }
        )
    runs = [
        {"id": row.id, "status": row.status, "progress": row.progress}
        for row in db.scalars(
            select(BacktestRun).order_by(BacktestRun.queued.desc()).limit(4)
        )
    ]
    notes = (
        [
            {
                "category": note.category,
                "severity": note.severity,
                "created": note.created,
            }
            for note in db.scalars(
                select(Notification)
                .where(
                    Notification.expires > clock,
                    ~Notification.series.like("THNDR_PORTFOLIO:%"),
                )
                .order_by(Notification.created.desc())
                .limit(5)
            )
        ]
        if settings.in_app
        else []
    )
    try:
        broker = await thndr_status()
        broker_state = {"status": broker.status, "last_sync": broker.last_sync}
    except HTTPException:
        broker_state = {"status": "DEGRADED", "last_sync": None}
    solver = ai_status()
    from app.services.scanner_repository import load_settings

    manual = load_settings(db).manual
    return {
        "fastapi": "RUNNING",
        "database": "CONNECTED",
        "migration": {"current": version, "expected": SCHEMA, "ready": True},
        "market": market,
        "workers": pulses,
        "thndr": broker_state,
        "ai": solver,
        "channels": channels,
        "policy": {
            "kill_switch": policy.kill_switch,
            "islamic": policy.islamic_mode,
            "advanced": policy.advanced_required,
            "trade_cap": policy.max_trade_risk,
            "stock_cap": policy.max_stock_allocation,
        },
        "data": {
            "raw_tickers": raw_tickers,
            "current_raw_tickers": current_raw,
            "approved_datasets": approved,
            "latest": latest_ingest.report["source_timestamp"]
            if latest_ingest
            else None,
            "realtime": False,
        },
        "failed": {
            "scan": db.scalar(
                select(func.count())
                .select_from(ScheduledJob)
                .where(ScheduledJob.status == "FAILED")
            ),
            "backtest": db.scalar(
                select(func.count())
                .select_from(BacktestRun)
                .where(BacktestRun.status == "FAILED")
            ),
            "paper": db.scalar(
                select(func.count())
                .select_from(PaperAccount)
                .where(PaperAccount.failure.is_not(None))
            ),
            "delivery": sum(c.get("FAILED", 0) for c in channels.values()),
        },
        "opportunities": entry[:6],
        "reviews": review[:6],
        "virtual": virtual,
        "backtests": runs,
        "notifications": notes,
        "manual": {
            "equity": manual.equity,
            "cash": manual.settled_cash,
            "as_of": manual.as_of,
            "holdings": [
                {"ticker": x.ticker, "shares": x.shares}
                for x in (manual.positions or [])[:6]
            ],
        }
        if manual
        else None,
    }
