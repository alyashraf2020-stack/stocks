"""SQLite writer transactions serialize claims, settings changes and publication."""

import hashlib
import json
import time
from contextlib import contextmanager
from datetime import UTC
from uuid import uuid4

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.sqlite import insert

from app.models.market_scan import MarketScan
from app.models.notification import Notification
from app.models.notification_outbox import NotificationOutbox
from app.models.scheduled_job import (
    ScannerAudit,
    ScannerControl,
    ScannerHeartbeat,
    ScheduledJob,
)
from app.models.trading_signal import TradingSignal
from app.schemas.scanner import ENV, ScannerSettings

MAX_ATTEMPTS = 3


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@contextmanager
def writer(db):
    if db.in_transaction():
        raise RuntimeError("Scanner writer requires a fresh database session")
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def load_settings(db):
    row = db.get(ScannerControl, 1)
    if row:
        return ScannerSettings.model_validate(row.settings)
    return ScannerSettings(
        enabled=ENV.SCANNER_ENABLED,
        interval_seconds=ENV.SCANNER_INTERVAL_SECONDS,
    )


def save_settings(db, new):
    with writer(db):
        current = load_settings(db)
        if new.revision != current.revision:
            return None
        if new == current:
            return current
        new = new.model_copy(update={"revision": current.revision + 1})
        payload = new.model_dump(mode="json")
        stmt = insert(ScannerControl).values(
            id=1, revision=new.revision, settings=payload
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={"revision": new.revision, "settings": payload},
            )
        )
        action = "ENABLED" if new.enabled else "PAUSED"
        if new.enabled == current.enabled:
            action = "SETTINGS_UPDATED"
        db.add(ScannerAudit(at=time.time(), action=action, revision=new.revision))
    return new


def enqueue(db, cal, now, *, manual=False):
    with writer(db):
        settings = load_settings(db)
        session = cal["completed_session"]
        if (
            not session
            or settings.interval_seconds
            or (not manual and not settings.enabled)
        ):
            return None
        # Manual runs collapse while pending/running and within the same minute.
        if manual:
            queued = db.scalar(
                select(ScheduledJob)
                .where(
                    ScheduledJob.revision == settings.revision,
                    ScheduledJob.status.in_(["PENDING", "RUNNING"]),
                )
                .limit(1)
            )
            if queued:
                return queued.id
        key = f"{settings.revision}:{settings.mode}:{session}"
        if manual:
            key += f":manual:{int(now // 60)}"
        inserted = db.execute(
            insert(ScheduledJob)
            .values(
                window=key,
                session=session,
                revision=settings.revision,
                mode=settings.mode,
                status="PENDING",
                due=now,
                queued=now,
                attempts=0,
            )
            .on_conflict_do_nothing(index_elements=["window"])
        )
        job_id = db.scalar(select(ScheduledJob.id).where(ScheduledJob.window == key))
        if manual and inserted.rowcount == 1:
            db.add(
                ScannerAudit(
                    at=now,
                    action="MANUAL_REQUEST",
                    revision=settings.revision,
                    job_id=job_id,
                )
            )
        return job_id


def heartbeat(db, worker_id, now, job_id=None):
    with writer(db):
        db.merge(ScannerHeartbeat(worker_id=worker_id, seen=now, job_id=job_id))


def fence(job_id, token, now):
    return (
        ScheduledJob.id == job_id,
        ScheduledJob.status == "RUNNING",
        (ScheduledJob.token == token),
        ScheduledJob.lease_until > now,
    )


def renew(db, job_id, token, now):
    with writer(db):
        result = db.execute(
            update(ScheduledJob)
            .where(*fence(job_id, token, now))
            .values(
                lease_until=now + ENV.SCANNER_LEASE_SECONDS,
            )
        )
        return result.rowcount == 1


def claim(db, now):
    with writer(db):
        settings = load_settings(db)
        db.execute(
            update(ScheduledJob)
            .where(
                ScheduledJob.status == "RUNNING",
                ScheduledJob.lease_until <= now,
                ScheduledJob.attempts >= MAX_ATTEMPTS,
            )
            .values(status="FAILED", error="LEASE_EXHAUSTED", finished=now, token=None)
        )
        db.execute(
            update(ScheduledJob)
            .where(
                ScheduledJob.status == "RUNNING",
                ScheduledJob.lease_until <= now,
            )
            .values(status="PENDING", due=now, error="LEASE_RECOVERED", token=None)
        )
        db.execute(
            update(ScheduledJob)
            .where(
                ScheduledJob.status == "PENDING",
                ScheduledJob.revision != settings.revision,
            )
            .values(status="CANCELLED", error="SETTINGS_CHANGED", finished=now)
        )
        if db.scalar(
            select(ScheduledJob.id).where(ScheduledJob.status == "RUNNING").limit(1)
        ):
            return None
        job = db.scalar(
            select(ScheduledJob)
            .where(
                ScheduledJob.status == "PENDING",
                ScheduledJob.due <= now,
            )
            .order_by(ScheduledJob.due, ScheduledJob.id)
            .limit(1)
        )
        if not job:
            return None
        job.status = "RUNNING"
        job.started = now
        job.token = uuid4().hex
        job.lease_until = now + ENV.SCANNER_LEASE_SECONDS
        job.attempts += 1
        return job.id, job.token


def fail(db, job_id, token, now, error):
    from app.services.notification_service import emit

    with writer(db):
        job = db.scalar(select(ScheduledJob).where(*fence(job_id, token, now)))
        if not job:
            return False
        job.error = error
        job.token = None
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.finished = "FAILED", now
            emit(
                db,
                load_settings(db),
                now,
                "SCANNER_FAILURE",
                "WARNING",
                {"reason": error, "limitations": ["SCAN_FAILED"]},
                error,
            )
        else:
            job.status, job.due = "PENDING", now + 15 * 2 ** (job.attempts - 1)
        return True


def reserve_broker_check(db, now):
    with writer(db):
        current = load_settings(db)
        stmt = insert(ScannerControl).values(
            id=1,
            revision=current.revision,
            settings=current.model_dump(mode="json"),
            last_broker_check=now,
        )
        result = db.execute(
            stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={"last_broker_check": now},
                where=(
                    ScannerControl.last_broker_check.is_(None)
                    | (
                        ScannerControl.last_broker_check
                        <= now - ENV.SCANNER_THNDR_MIN_INTERVAL_SECONDS
                    )
                ),
            )
        )
        return result.rowcount == 1


def prune(db, now):
    cutoff = now - ENV.SCANNER_HISTORY_RETENTION_DAYS * 86400
    with writer(db):
        expired = select(Notification.id).where(Notification.created < cutoff)
        db.execute(
            delete(NotificationOutbox).where(
                NotificationOutbox.notification_id.in_(expired)
            )
        )
        db.execute(delete(Notification).where(Notification.created < cutoff))
        db.execute(delete(TradingSignal).where(TradingSignal.updated < cutoff))
        db.execute(delete(MarketScan).where(MarketScan.created < cutoff))
        db.execute(delete(ScheduledJob).where(ScheduledJob.finished < cutoff))
        db.execute(delete(ScannerHeartbeat).where(ScannerHeartbeat.seen < cutoff))
        db.execute(delete(ScannerAudit).where(ScannerAudit.at < cutoff))


def suppress_entry(row, *reasons):
    row["qualified"] = False
    if row["category"] in {"BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT"}:
        row["category"] = (
            "SHARIA_BLOCKED"
            if any(r.startswith("SHARIA_") for r in reasons)
            else "RISK_BLOCKED"
        )
    report = row.get("analysis")
    if not report:
        return
    report["risk_blockers"] = sorted(set(report["risk_blockers"] + list(reasons)))
    report["ai_explanation_ar"] = None
    report["suggested_shares"] = None
    if report["signal"] in {"BUY", "STRONG_BUY"}:
        report["signal"], report["decision"] = "WAIT", "PORTFOLIO_POLICY_BLOCK"
        report["explanation_ar"] = (
            "قواعد المخاطر أو حالة البيانات الحالية بتمنع اقتراح الدخول."
        )
    position = report["position"]
    if position:
        if position["action"] == "ADD_TO_POSITION":
            position["action"] = "WAIT"
        position["scenario_actions"] = [
            s for s in position["scenario_actions"] if s != "ADD_TO_POSITION"
        ]
        position["scenarios_ar"] = [
            s for s in position["scenarios_ar"] if not s.startswith("راجع زيادة المركز")
        ]


def publish(db, job_id, token, now, data):
    from datetime import datetime, timedelta

    from app.models.security import EGXSecurity
    from app.services.alert_engine import ENTRY, portfolio_alert, symbol_alerts
    from app.services.notification_service import emit
    from app.services.risk_policy import entry_blocks, load_policy
    from app.services.scanner_calendar import CAIRO, calendar_at
    from app.services.sharia_filter import status_for

    with writer(db):
        job = db.scalar(select(ScheduledJob).where(*fence(job_id, token, now)))
        if not job:
            return False
        settings = load_settings(db)
        if settings.revision != job.revision:
            job.status, job.error, job.finished, job.token = (
                "CANCELLED",
                "SETTINGS_CHANGED",
                now,
                None,
            )
            return False
        timestamp = datetime.fromtimestamp(now, UTC)
        market = calendar_at(timestamp)
        policy = load_policy(db)
        policy_changed = policy.model_dump(mode="json") != data.get("policy")
        if policy.kill_switch:
            emit(
                db,
                settings,
                now,
                "KILL_SWITCH",
                "CRITICAL",
                {"reason": "KILL_SWITCH", "limitations": ["READ_ONLY_MONITORING"]},
                [job.session, policy.model_dump(mode="json")],
            )
        error = data.get("error")
        if error:
            category = (
                "THNDR_CONNECTION" if error.startswith("THNDR_") else "SCANNER_FAILURE"
            )
            emit(
                db,
                settings,
                now,
                category,
                "WARNING",
                {"reason": error},
                error,
                settings.mode,
            )
        if not policy_changed:
            portfolio_alert(
                db, settings, now, data.get("portfolio_risk"), data.get("broker_sync")
            )
        actual = []
        ai_tokens = 0
        unchanged = 0
        for fingerprint, row, cached in data["rows"]:
            saved = db.get(TradingSignal, (settings.mode, row["ticker"]))
            report = row.get("analysis")
            if report:
                security = db.get(EGXSecurity, row["ticker"])
                screen = (
                    status_for(db, security, timestamp.astimezone(CAIRO).date())[
                        "status"
                    ]
                    if security
                    else "UNVERIFIED"
                )
                reasons = entry_blocks(
                    policy,
                    screen,
                    advanced_supported=settings.mode.endswith("_PORTFOLIO"),
                )
                if policy_changed:
                    reasons.append("POLICY_CHANGED")
                if (
                    row.get("qualified")
                    and data.get("portfolio_as_of")
                    and (
                        timestamp - datetime.fromisoformat(data["portfolio_as_of"])
                        > timedelta(minutes=policy.max_snapshot_minutes)
                    )
                ):
                    reasons.append("CURRENT_SNAPSHOT")
                if report.get("sharia_status") != screen:
                    reasons.append("SCREENING_CHANGED")
                if market["completed_session"] != job.session:
                    reasons.append("SESSION_CHANGED")
                if market["session_status"] == "HALTED":
                    reasons.append("MARKET_HALTED")
                if (
                    not security
                    or security.listing_status != "ACTIVE"
                    or security.isin != row["observation"]["instrument_id"]
                ):
                    reasons.append("INSTRUMENT_CHANGED")
                if reasons:
                    suppress_entry(row, *reasons)
                report["sharia_status"] = screen
                usage = report.get("usage") or {}
                if not cached:
                    ai_tokens += usage.get("input_tokens", 0) + usage.get(
                        "output_tokens", 0
                    )
            if not cached or (saved and saved.data != row):
                symbol_alerts(
                    db,
                    settings,
                    now,
                    row,
                    saved.data if saved else {},
                    fingerprint,
                    data.get("broker_sync"),
                )
            elif cached:
                unchanged += 1
            # A policy/calendar change cannot populate the reusable snapshot cache.
            if not policy_changed and market["completed_session"] == job.session:
                db.merge(
                    TradingSignal(
                        scope=settings.mode,
                        ticker=row["ticker"],
                        fingerprint=fingerprint,
                        updated=now,
                        data=row,
                    )
                )
            actual.append(row)
        actual.sort(key=lambda row: (-(row["rank"] or 0), row["ticker"]))
        db.add(
            MarketScan(
                job_id=job_id,
                created=now,
                summary={
                    "mode": job.mode,
                    "session": job.session,
                    "duration_seconds": round(max(0, now - job.started), 2),
                    "analyzed": sum(r["analysis"] is not None for r in actual)
                    - unchanged,
                    "scanned": len(actual),
                    "unchanged": unchanged,
                    "opportunities": sum(r["category"] in ENTRY for r in actual),
                    "blocked": sum(
                        r["category"] in {"RISK_BLOCKED", "SHARIA_BLOCKED"}
                        for r in actual
                    ),
                    "unavailable": [
                        r["ticker"] for r in actual if r["category"] == "UNAVAILABLE"
                    ],
                    "unscanned": data.get("unscanned", []),
                    "provider_error": error,
                    "notice": data.get("notice"),
                    "portfolio_as_of": data.get("portfolio_as_of"),
                    "ai_tokens": ai_tokens,
                    "market": market,
                    "policy_digest": digest(policy.model_dump(mode="json")),
                    "broker_sync": data.get("broker_sync"),
                },
                results=actual,
            )
        )
        job.status = "FAILED" if error else "SUCCEEDED"
        job.error, job.finished, job.token = error, now, None
        return True
