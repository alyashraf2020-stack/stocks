import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner, portfolio
from app.api.v1.endpoints.trading_readiness import connection_status
from app.core.database import get_db
from app.models.order_event import OrderEvent
from app.models.order_proposal import OrderProposal
from app.schemas.order_proposal import (
    DraftRequest,
    ExactReview,
    ReviewRequest,
    TradingSettings,
)
from app.services import order_approval
from app.services import order_proposal_service as service
from app.services.risk_policy import load_policy
from app.services.scanner_broker import local_broker_state
from app.services.scanner_calendar import CAIRO
from app.services.scanner_repository import writer
from app.services.trading_readiness import readiness

router = APIRouter(prefix="/orders", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]
COOKIE = "__Host-egx-order-review"


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except service.ProposalError as exc:
        code = str(exc)
        status = (
            404
            if code == "UNKNOWN_DRAFT"
            else 429
            if code.endswith("RATE_LIMIT")
            else 409
        )
        raise HTTPException(status, code) from None


@router.get("/settings", response_model=TradingSettings)
def settings(db: DB):
    return service.settings(db)


@router.post("/settings", response_model=TradingSettings)
def save_settings(payload: TradingSettings, db: DB):
    with writer(db):
        return checked(service.set_settings, db, payload)


@router.get("/proposals")
def listing(
    db: DB, offset: int = Query(0, ge=0, le=10000), limit: int = Query(30, ge=1, le=100)
):
    now = datetime.now(CAIRO)
    with writer(db):
        service.sweep(db, now)
        rows = list(
            db.scalars(
                select(OrderProposal)
                .order_by(OrderProposal.created.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        for row in rows:
            service.invalidate_if_needed(db, row, now)
        return [service.view(row) for row in rows]


async def requested_snapshot(payload):
    if payload.source != "THNDR":
        return None
    try:
        snapshot = await portfolio()
    except HTTPException:
        raise HTTPException(409, "AUTHORIZED_PORTFOLIO_UNAVAILABLE") from None
    if not snapshot.last_sync:
        raise HTTPException(409, "AUTHORIZED_PORTFOLIO_UNAVAILABLE")
    return snapshot


@router.post("/proposals", status_code=201)
async def create(payload: DraftRequest, db: DB):
    snapshot = await requested_snapshot(payload)
    with writer(db):
        row = checked(service.create, db, payload, datetime.now(CAIRO), broker=snapshot)
        return service.view(row)


@router.get("/proposals/{key}")
async def detail(key: UUID, request: Request, db: DB):
    connection = await connection_status()
    now = datetime.now(CAIRO)
    with writer(db):
        row = checked(service.by_id, db, key)
        service.invalidate_if_needed(db, row, now)
        data = service.view(row)
        data["readiness"] = readiness(
            db,
            now,
            connection,
            load_policy(db),
            draft=row.data,
            https=request.url.scheme == "https",
        )
        return data


@router.get("/proposals/{key}/events")
def history(key: UUID, db: DB):
    row = checked(service.by_id, db, key)
    return [
        {"kind": item.kind, "created": item.created, **item.evidence}
        for item in db.scalars(
            select(OrderEvent)
            .where(OrderEvent.proposal_id == row.id)
            .order_by(OrderEvent.id)
        )
    ]


@router.post("/proposals/{key}/refresh")
async def refresh(key: UUID, payload: DraftRequest, db: DB):
    snapshot = await requested_snapshot(payload)
    with writer(db):
        old = checked(service.by_id, db, key)
        row = checked(
            service.create,
            db,
            payload,
            datetime.now(CAIRO),
            broker=snapshot,
            parent=old,
        )
        return service.view(row)


@router.post("/proposals/{key}/reject")
def reject(key: UUID, db: DB):
    now = datetime.now(CAIRO)
    with writer(db):
        row = checked(service.by_id, db, key)
        service.invalidate_if_needed(db, row, now)
        if row.state in service.ACTIVE:
            service.transition(
                db, row, "CANCELLED", now.timestamp(), "OWNER_REJECTED_LOCAL_DRAFT"
            )
        return service.view(row)


def require_https(request):
    if request.url.scheme != "https":
        raise HTTPException(403, "HTTPS_REQUIRED")


@asynccontextmanager
async def review_source(db, key):
    existing = checked(service.by_id, db, key)
    expected = existing.data["broker_snapshot_at"]
    broker_draft = existing.data["source"] == "THNDR"
    db.rollback()
    if broker_draft:
        async with local_broker_state(expected) as allowed:
            if not expected or not allowed:
                raise HTTPException(409, "AUTHORIZED_PORTFOLIO_UNAVAILABLE")
            yield
    else:
        yield


@router.post("/proposals/{key}/review")
async def review(
    key: UUID, payload: ReviewRequest, request: Request, response: Response, db: DB
):
    require_https(request)
    session = request.cookies.get(COOKIE) or secrets.token_urlsafe(32)
    async with review_source(db, key):
        with writer(db):
            row = checked(service.by_id, db, key)
            result = checked(
                order_approval.issue,
                db,
                row,
                payload.fingerprint,
                datetime.now(CAIRO),
                session,
            )
    if result is None:
        raise HTTPException(409, "REVIEW_NO_LONGER_AVAILABLE")
    response.set_cookie(
        COOKIE,
        session,
        secure=True,
        httponly=True,
        samesite="strict",
        max_age=1800,
        path="/",
    )
    return result


@router.post("/proposals/{key}/confirm-local")
async def confirm(key: UUID, payload: ExactReview, request: Request, db: DB):
    require_https(request)
    async with review_source(db, key):
        with writer(db):
            row = checked(service.by_id, db, key)
            error = checked(
                order_approval.confirm,
                db,
                row,
                payload,
                datetime.now(CAIRO),
                request.cookies.get(COOKIE),
            )
            data = service.view(row)
    if error:
        raise HTTPException(409, error)
    return data


@router.post("/proposals/{key}/handoff")
def handoff(key: UUID, db: DB):
    checked(service.by_id, db, key)
    raise HTTPException(409, "LIVE_CAPABILITY_DISABLED")
