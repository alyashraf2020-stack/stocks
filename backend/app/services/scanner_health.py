from sqlalchemy import func, select

from app.models.market_scan import MarketScan
from app.models.notification import Notification
from app.models.scheduled_job import ScannerHeartbeat, ScheduledJob
from app.schemas.scanner import ENV
from app.services.scanner_repository import load_settings
from app.workers.trading_scheduler import EOD_GRACE_SECONDS, eod_due


def health(db, now, market):
    settings = load_settings(db)
    heartbeat = db.scalar(
        select(ScannerHeartbeat).order_by(ScannerHeartbeat.seen.desc()).limit(1)
    )
    last = db.scalar(
        select(ScheduledJob.finished)
        .where(
            ScheduledJob.status == "SUCCEEDED",
            ScheduledJob.revision == settings.revision,
        )
        .order_by(ScheduledJob.finished.desc())
        .limit(1)
    )
    job = db.scalar(select(ScheduledJob).order_by(ScheduledJob.id.desc()).limit(1))
    due = db.scalar(
        select(func.min(ScheduledJob.due)).where(
            ScheduledJob.status == "PENDING",
            ScheduledJob.revision == settings.revision,
        )
    )
    active = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.expires > now,
            Notification.acknowledged_at.is_(None),
        )
    )
    run = db.get(MarketScan, job.id) if job else None
    if due is None and settings.enabled and settings.interval_seconds == 0:
        key = f"{settings.revision}:{settings.mode}:{market['completed_session']}"
        scheduled = db.scalar(select(ScheduledJob.id).where(ScheduledJob.window == key))
        if not scheduled and eod_due(market) is not None:
            due = max(now, eod_due(market))
        elif market["next_close"]:
            due = market["next_close"] + EOD_GRACE_SECONDS
    return {
        "enabled": settings.enabled,
        "mode": settings.mode,
        "interval_seconds": settings.interval_seconds,
        "supported_intervals": [0],
        "intraday_blocker": "LICENSED_INTRADAY_FEED_REQUIRED",
        "worker_online": bool(
            heartbeat and 0 <= now - heartbeat.seen <= ENV.SCANNER_HEARTBEAT_SECONDS * 3
        ),
        "last_heartbeat": heartbeat.seen if heartbeat else None,
        "last_success": last,
        "next_scheduled": due,
        "job_status": job.status if job else None,
        "job_error": job.error if job else None,
        "market": market,
        "active_alerts": active,
        "last_summary": run.summary if run else None,
    }
