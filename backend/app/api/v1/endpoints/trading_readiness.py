from datetime import datetime
from time import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.v1.endpoints.integrations import owner, status
from app.core.database import get_db
from app.integrations.thndr_auth import IntegrationError, Vault
from app.schemas.thndr import Connection
from app.services.risk_policy import load_policy
from app.services.scanner_calendar import CAIRO
from app.services.trading_readiness import readiness

router = APIRouter(prefix="/trading-readiness", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


async def connection_status():
    try:
        connection = await status()
        if connection.status == "CONNECTED":
            async with Vault().locked() as state:
                token = state.get("tokens") or {}
                if (
                    state.get("revoking")
                    or state.get("reauth")
                    or token.get("expires_at", 0) <= time()
                ):
                    return Connection(status="RECONNECT_REQUIRED")
        return connection
    except (HTTPException, IntegrationError):
        return Connection(status="RECONNECT_REQUIRED")


@router.get("")
async def report(request: Request, db: DB):
    return readiness(
        db,
        datetime.now(CAIRO),
        await connection_status(),
        load_policy(db),
        https=request.url.scheme == "https",
    )
