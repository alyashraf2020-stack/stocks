import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.models.notification import Notification
from app.models.notification_outbox import NotificationOutbox
from app.schemas.notification import AlertUpdate
from app.services.risk_policy import load_policy
from app.services.scanner_broker import local_broker_snapshot
from app.services.scanner_repository import writer

router = APIRouter(prefix="/notifications", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


@router.get("")
async def notifications(
    db: DB, unread: bool = False, limit: int = Query(75, ge=1, le=100)
):
    from app.services.notification_delivery import SEVERITIES, prefs

    settings = prefs(db)
    if not settings.in_app:
        return []
    policy = load_policy(db)
    sync = None
    broker_series = Notification.series.like("THNDR_PORTFOLIO:%")
    if db.scalar(select(Notification.id).where(broker_series).limit(1)):
        async with local_broker_snapshot() as sync:
            pass
    query = (
        select(Notification, NotificationOutbox)
        .join(
            NotificationOutbox,
            Notification.id == NotificationOutbox.notification_id,
        )
        .where(Notification.expires > time.time())
    )
    permitted = ~broker_series | (Notification.category == "THNDR_CONNECTION")
    if sync:
        permitted = permitted | (
            Notification.payload["_broker_sync"].as_string() == sync
        )
    query = query.where(permitted,
                        ~Notification.category.in_(settings.muted),
                        Notification.severity.in_(SEVERITIES[SEVERITIES.index(settings.severity):]))
    if unread:
        query = query.where(Notification.read_at.is_(None))
    rows = db.execute(query.order_by(Notification.created.desc()).limit(limit))
    return [
        {
            "id": row.id,
            "category": row.category,
            "severity": row.severity,
            "created": row.created,
            "expires": row.expires,
            "read_at": row.read_at,
            "acknowledged_at": row.acknowledged_at,
            "delivery": outbox.status,
            "attempts": outbox.history,
            **{
                key: value
                for key, value in row.payload.items()
                if not key.startswith("_")
            },
            # All persisted entry alerts are point-in-time observations. No link to execution.
            "requires_recheck": row.severity == "OPPORTUNITY" or policy.kill_switch,
        }
        for row, outbox in rows
    ]


@router.post("/{alert_id}")
def mark(alert_id: str, update: AlertUpdate, db: DB):
    if len(alert_id) != 64:
        raise HTTPException(404, "UNKNOWN_ALERT")
    with writer(db):
        row = db.get(Notification, alert_id)
        if not row or row.expires <= time.time():
            raise HTTPException(404, "UNKNOWN_ALERT")
        now = time.time()
        row.read_at = (
            (row.read_at or now) if update.read or update.acknowledge else None
        )
        if update.acknowledge:
            row.acknowledged_at = row.acknowledged_at or now
    return {"updated": True}
