"""In-app persistence and a leased, at-least-once external delivery interface."""

from typing import Protocol
from uuid import uuid4

from sqlalchemy import select

from app.models.notification import Notification
from app.models.notification_outbox import NotificationOutbox
from app.schemas.scanner import ENV
from app.services.scanner_repository import digest, writer

SEVERITIES = ("INFO", "OPPORTUNITY", "WARNING", "CRITICAL")
CATEGORIES = frozenset(
    {
        "BUY_REVIEW",
        "SELL_REVIEW",
        "ENTRY_ZONE",
        "BREAKOUT",
        "RATING_CHANGE",
        "STOP",
        "TARGET",
        "PORTFOLIO_RISK",
        "SHARIA_CHANGE",
        "MARKET_DATA",
        "THNDR_CONNECTION",
        "SCANNER_FAILURE",
        "KILL_SWITCH",
        "TECHNICAL_CHANGE",
        "PAPER_FILL",
        "PAPER_REJECTED",
        "BACKTEST_COMPLETED",
        "BACKTEST_FAILED",
    }
)


class NotificationAdapter(Protocol):
    def deliver(self, notification_id: str, payload: dict) -> None: ...


class RetryDelivery(Exception):
    def __init__(self, seconds):
        self.seconds = max(1, min(seconds, 86400))


def emit(db, settings, now, category, severity, facts, identity, scope=""):
    if severity != "CRITICAL" and (
        category in settings.muted_categories
        or SEVERITIES.index(severity) < SEVERITIES.index(settings.minimum_severity)
    ):
        return
    series = ":".join((scope, category, facts.get("ticker") or ""))
    alert_id = digest([series, identity])
    if db.get(Notification, alert_id):
        return
    prior = db.scalar(
        select(Notification.created)
        .where(
            Notification.series == series,
        )
        .order_by(Notification.created.desc())
        .limit(1)
    )
    if (
        prior is not None
        and severity != "CRITICAL"
        and now - prior < ENV.ALERT_COOLDOWN_SECONDS
    ):
        return
    payload = {
        "source_timestamp": None,
        "freshness": "UNKNOWN",
        "limitations": [],
        "executable": False,
        **facts,
    }
    db.add(
        Notification(
            id=alert_id,
            series=series,
            category=category,
            severity=severity,
            created=now,
            expires=now + (86400 if severity == "OPPORTUNITY" else 7 * 86400),
            payload=payload,
        )
    )
    db.add(
        NotificationOutbox(
            notification_id=alert_id,
            status="IN_APP",
            due=now,
            history=[],
        )
    )
    db.flush()
    from app.services.notification_delivery import fanout

    fanout(db, alert_id)


def deliver_one(db_factory, adapter: NotificationAdapter, clock):
    """Only an opted-in channel may enqueue PENDING. Phase 5 enables IN_APP only."""
    with db_factory() as db, writer(db):
        now = clock()
        row = db.scalar(
            select(NotificationOutbox)
            .join(
                Notification,
                Notification.id == NotificationOutbox.notification_id,
            )
            .where(
                NotificationOutbox.status.in_(["PENDING", "SENDING"]),
                NotificationOutbox.due <= now,
                NotificationOutbox.attempts < 5,
                Notification.expires > now,
            )
            .order_by(NotificationOutbox.due)
            .limit(1)
        )
        if not row:
            return False
        key, token = row.notification_id, uuid4().hex
        row.status, row.token, row.due = "SENDING", token, now + 120
        row.attempts += 1
        # Deliberate allowlist. No ticker, prices, holdings, or other private fields.
        payload = {"category": db.get(Notification, key).category}
    retry = None
    try:
        adapter.deliver(key, payload)
    except RetryDelivery as error:
        retry = error.seconds
    except Exception:  # noqa: BLE001 — Outbox retries cannot expose adapter responses.
        retry = 30
    with db_factory() as db, writer(db):
        row = db.get(NotificationOutbox, key)
        if row is not None and row.token == token:
            now = clock()
            row.history = [
                *row.history,
                {"at": now, "result": "RETRY" if retry else "DELIVERED"},
            ]
            row.token = None
            if retry:
                row.status = "FAILED" if row.attempts >= 5 else "PENDING"
                row.due = now + max(retry, 15 * 2 ** (row.attempts - 1))
            else:
                row.status = "DELIVERED"
    return True
