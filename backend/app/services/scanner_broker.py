"""Check local grant and snapshot state without adding brokerage calls."""

import time
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime

from app.integrations.thndr_auth import IntegrationError, Vault


@asynccontextmanager
async def local_broker_snapshot():
    async with AsyncExitStack() as stack:
        try:
            data = await stack.enter_async_context(Vault().locked())
        except IntegrationError:
            data = {}
        synced = (data.get("portfolio") or {}).get("last_sync")
        authorized = bool(
            synced
            and not data.get("revoking")
            and not data.get("reauth")
            and (data.get("tokens") or {}).get("expires_at", 0) > time.time()
        )
        yield datetime.fromisoformat(synced).isoformat() if authorized else None


@asynccontextmanager
async def local_broker_state(expected_sync=None):
    async with local_broker_snapshot() as sync:
        yield bool(
            sync
            and (
                not expected_sync
                or sync == datetime.fromisoformat(expected_sync).isoformat()
            )
        )
