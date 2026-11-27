"""Owner-only EODHD settings, manual synchronization and quota visibility."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from filelock import Timeout
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.integrations import owner
from app.core.database import get_db
from app.schemas.thndr import Ticker
from app.services import eodhd as service
from app.services.data_provider.eodhd import ProviderError

router = APIRouter(prefix="/data/eodhd", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    token: str | None = None
    enabled: bool
    automatic: bool
    retry: bool
    exclusive: bool


class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Ticker


def command(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except Timeout:
        raise HTTPException(409, "SYNC_BUSY") from None
    except ProviderError as error:
        code = str(error)
        status = 429 if code in {"FREE_QUOTA_EXHAUSTED", "RATE_LIMITED"} else 409
        raise HTTPException(status, code) from None


@router.get("")
def status(db: DB):
    return service.status(db, service.utcnow())


@router.post("/settings")
async def configure(request: Request, db: DB):
    # FastAPI's default validation response includes rejected inputs. Keep the
    # credential out of that path, including invalid JSON or unknown fields.
    content = bytearray()
    async for block in request.stream():
        if len(content) + len(block) > 2048:
            raise HTTPException(422, "INVALID_SETTINGS")
        content.extend(block)
    try:
        settings = Configuration.model_validate(json.loads(content))
    except (ValueError, ValidationError, RecursionError):
        raise HTTPException(422, "INVALID_SETTINGS") from None
    await run_in_threadpool(
        command,
        service.configure,
        db,
        settings.model_dump(exclude={"token"}),
        settings.token,
    )
    return await run_in_threadpool(status, db)


@router.post("/disconnect")
def disconnect(db: DB):
    command(service.remove_token, db)
    return status(db)


@router.post("/test")
def test_connection(db: DB):
    return command(service.network, db, "test")


@router.post("/catalog")
def update_catalog(db: DB):
    return command(service.network, db, "catalog")


@router.post("/sync")
def sync(payload: Instrument, db: DB):
    return command(service.network, db, "history", ticker=payload.ticker)
