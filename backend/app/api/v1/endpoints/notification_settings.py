import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.integrations.telegram_client import TransportError
from app.integrations.web_push import validate_device
from app.models.delivery import ChannelDelivery, DeliveryTarget
from app.schemas.notification_settings import DeliveryPreferences, PushDevice
from app.services import notification_delivery as delivery
from app.services.scanner_repository import writer

router = APIRouter(prefix="/notification-settings", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


def checked(callback, *args):
    try:
        return callback(*args)
    except TransportError as exc:
        raise HTTPException(
            429 if exc.code.endswith("RATE_LIMITED") else 422, exc.code
        ) from None
    except ValueError as exc:
        raise HTTPException(
            409 if str(exc) == "SETTINGS_CHANGED" else 422, str(exc)
        ) from None


@router.get("")
def settings(db: DB):
    environment = delivery.env()
    configured = delivery.configuration(environment)
    return {
        "preferences": delivery.prefs(db),
        "configured": configured,
        "vapid_public_key": environment.VAPID_PUBLIC_KEY
        if configured["PUSH"]
        else None,
        "targets": [
            {
                "id": x.id,
                "channel": x.channel,
                "label": x.label,
                "active": x.active,
                "since": x.since,
                "last_ok": x.last_ok,
            }
            for x in db.scalars(
                select(DeliveryTarget).order_by(DeliveryTarget.since.desc()).limit(50)
            )
        ],
        "delivery_counts": delivery.recent_status(db),
        "recent": [
            {
                "channel": x.channel,
                "status": x.status,
                "created": x.created,
                "attempts": x.attempts,
                "error": x.error,
                "history": x.history,
            }
            for x in db.scalars(
                select(ChannelDelivery)
                .order_by(ChannelDelivery.created.desc())
                .limit(25)
            )
        ],
    }


@router.post("")
def save(data: DeliveryPreferences, db: DB):
    return checked(delivery.set_prefs, db, data, time.time())


@router.post("/telegram/pair")
def pair(db: DB):
    return checked(delivery.pair_start, db, time.time(), delivery.env())


@router.post("/telegram/check")
def check(db: DB):
    factory = sessionmaker(bind=db.get_bind(), autoflush=False)
    return checked(delivery.pair_check, factory, time.time(), delivery.env())


@router.post("/devices")
def add(device: PushDevice, db: DB):
    environment = delivery.env()
    if not delivery.configuration(environment)["PUSH"]:
        raise HTTPException(422, "PUSH_NOT_CONFIGURED")
    checked(validate_device, device)
    with writer(db):
        key = checked(
            delivery.install_target,
            db,
            "PUSH",
            device.name,
            device.endpoint,
            device.model_dump(exclude={"name"}),
            time.time(),
            environment,
        )
    return {"id": key}


@router.post("/targets/{key}/revoke")
def remove(key: str, db: DB):
    if not delivery.revoke(db, key):
        raise HTTPException(404, "UNKNOWN_DESTINATION")
    return {"revoked": True}


@router.post("/targets/{key}/test")
def test_delivery(key: str, channel: Literal["TELEGRAM", "PUSH"], db: DB):
    checked(delivery.test_message, db, channel, key, time.time(), delivery.env())
    return {"queued": True}
