from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.models.paper_account import PaperAccount
from app.models.paper_ledger import PaperLedger
from app.models.paper_order import PaperOrder
from app.models.paper_trade import PaperTrade
from app.schemas.paper_trading import (
    AccountControl,
    AccountCreate,
    CashRequest,
    OrderRequest,
)
from app.services import paper_trading as paper
from app.services.scanner_calendar import CAIRO

router = APIRouter(prefix="/paper-trading", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as error:
        reason = str(error)
        if not reason.replace("_", "").isalnum() or len(reason) > 90:
            reason = "INVALID_VIRTUAL_REQUEST"
        status_code = (
            404
            if reason in {"UNKNOWN_VIRTUAL_ACCOUNT", "UNKNOWN_VIRTUAL_ORDER"}
            else (409 if reason == "IDEMPOTENCY_KEY_CONFLICT" else 422)
        )
        raise HTTPException(status_code, reason) from None


@router.get("/accounts")
def accounts(db: DB):
    rows = db.scalars(
        select(PaperAccount).order_by(PaperAccount.created.desc()).limit(100)
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "capital": row.start_capital,
            "strategy": row.strategy,
            "archived": row.archived,
            "automated": row.automated,
            "virtual": True,
        }
        for row in rows
    ]


@router.post("/accounts", status_code=201)
def create(request: AccountCreate, db: DB):
    return {
        "id": checked(paper.create, db, request, datetime.now(CAIRO)),
        "virtual": True,
    }


@router.get("/accounts/{account}")
def portfolio(account: UUID, db: DB):
    return checked(paper.view, db, checked(paper.account_for, db, account))


@router.post("/accounts/{account}/settings")
def settings(account: UUID, request: AccountControl, db: DB):
    checked(paper.settings, db, account, request, datetime.now(CAIRO))
    return {"updated": True}


@router.post("/accounts/{account}/archive")
def archive(account: UUID, db: DB):
    checked(paper.archive, db, account, datetime.now(CAIRO))
    return {"archived": True}


@router.post("/accounts/{account}/cash")
def cash(account: UUID, request: CashRequest, db: DB):
    checked(paper.cash_change, db, account, request, datetime.now(CAIRO))
    return {"updated": True}


@router.get("/accounts/{account}/orders")
def orders(
    account: UUID,
    db: DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    row = checked(paper.account_for, db, account)
    records = db.scalars(
        select(PaperOrder)
        .where(PaperOrder.account_id == row.id)
        .order_by(PaperOrder.data["created"].as_string().desc(), PaperOrder.id)
        .offset(offset)
        .limit(limit)
    )
    return [record.data for record in records]


@router.post("/accounts/{account}/orders", status_code=201)
def order(account: UUID, request: OrderRequest, db: DB):
    return checked(paper.submit, db, account, request, datetime.now(CAIRO))


@router.post("/accounts/{account}/orders/{order_key}/cancel")
def cancel(account: UUID, order_key: UUID, db: DB):
    return checked(paper.cancel, db, account, order_key)


@router.get("/accounts/{account}/history")
def history(
    account: UUID,
    db: DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    row = checked(paper.account_for, db, account)
    trades = db.scalars(
        select(PaperTrade)
        .where(PaperTrade.account_id == row.id)
        .order_by(PaperTrade.id.desc())
        .offset(offset)
        .limit(limit)
    )
    ledger = db.scalars(
        select(PaperLedger)
        .where(PaperLedger.account_id == row.id)
        .order_by(PaperLedger.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "virtual": True,
        "trades": [record.data for record in trades],
        "ledger": [
            {
                "id": record.id,
                "created": record.created,
                "kind": record.kind,
                "data": record.data,
            }
            for record in ledger
        ],
    }


@router.get("/accounts/{account}/history/export.json")
def export(account: UUID, db: DB):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    row = checked(paper.account_for, db, account)
    trades = db.scalars(
        select(PaperTrade)
        .where(PaperTrade.account_id == row.id)
        .order_by(PaperTrade.id)
    )
    records = db.scalars(
        select(PaperLedger)
        .where(PaperLedger.account_id == row.id)
        .order_by(PaperLedger.id)
    )
    return JSONResponse(
        jsonable_encoder(
            {
                "virtual": True,
                "trades": [item.data for item in trades],
                "ledger": [
                    {
                        "id": item.id,
                        "created": item.created,
                        "kind": item.kind,
                        "data": item.data,
                    }
                    for item in records
                ],
            }
        ),
        headers={
            "Content-Disposition": 'attachment; filename="egx-virtual-history.json"'
        },
    )
