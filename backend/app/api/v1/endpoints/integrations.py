"""Single-owner integration endpoints, reachable only through authenticated ingress."""

import hmac
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.thndr_auth import (
    ISSUER,
    SCOPE,
    IntegrationError,
    ThndrOAuth,
    Vault,
    callback_uri,
)
from app.integrations.thndr_mcp import READ_TOOLS, readonly_session
from app.models.security import EGXSecurity
from app.schemas.thndr import Connection, Portfolio
from app.services.thndr_portfolio import synchronize

COOKIE = "__Host-egx-thndr-flow"


def owner(request: Request, response: Response):
    secret = os.getenv("INTEGRATIONS_GATEWAY_SECRET", "")
    presented = request.headers.get("X-EGX-Gateway", "")
    if len(secret) < 32 or not hmac.compare_digest(secret.encode(), presented.encode()):
        raise HTTPException(
            403, "OWNER_GATEWAY_REQUIRED", headers={"Cache-Control": "no-store"}
        )
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/integrations/thndr", dependencies=[Depends(owner)])


def public_error(exc):
    headers = {"Cache-Control": "no-store"}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return HTTPException(exc.status, exc.code, headers=headers)


@asynccontextmanager
async def operation():
    try:
        vault = Vault()
        async with (
            vault.locked() as data,
            httpx.AsyncClient(timeout=12, follow_redirects=False) as http,
        ):
            try:
                auth = ThndrOAuth(http)
                yield data, vault, auth
            except IntegrationError as exc:
                if exc.code == "RECONNECT_REQUIRED":
                    data["reauth"] = True
                    data.pop("portfolio", None)
                    data.pop("tools", None)
                if exc.code == "MISSING_PERMISSION":
                    data.pop("tools", None)
                    data.pop("portfolio", None)
                if exc.code == "UNEXPECTED_GRANT":
                    try:
                        await auth.revoke(data, vault.save)
                    except IntegrationError:
                        pass  # Revocation remains pending and all reads stay disabled.
                if exc.retry_after:
                    data["cooldown"] = time.time() + exc.retry_after
                data["error"] = exc.code
                vault.save(data)
                raise
    except IntegrationError as exc:
        raise public_error(exc) from None


def throttle(data, key, seconds):
    now = time.time()
    until = max(data.get("cooldown", 0), data.get(key, 0))
    if until > now:
        # Reject local bursts without pushing the original deadline forward.
        raise public_error(
            IntegrationError("RATE_LIMITED", 429, max(1, int(until - now + 0.999)))
        )
    data[key] = now + seconds


def status_view(data):
    granted = sorted(set(data.get("tools", [])) & READ_TOOLS)
    if data.get("revoking"):
        state = "REVOCATION_PENDING"
    elif data.get("reauth"):
        state = "RECONNECT_REQUIRED"
    elif data.get("tokens"):
        state = "CONNECTED"
    elif data.get("pending", {}).get("until", 0) > time.time():
        state = "AUTHORIZING"
    else:
        state = "DISCONNECTED"
    portfolio = data.get("portfolio") or {}
    freshness = {
        h["quote"]["freshness"]
        for h in portfolio.get("holdings") or []
        if h.get("quote")
    }
    return Connection(
        status=state,
        permissions=[SCOPE] if state == "CONNECTED" else [],
        available=granted,
        unavailable=sorted(READ_TOOLS - set(granted)),
        last_sync=portfolio.get("last_sync"),
        error=data.get("error"),
        freshness=freshness.pop() if len(freshness) == 1 else "UNKNOWN",
    )


@router.get("/status", response_model=Connection)
async def status():
    try:
        callback_uri()
        Vault()
    except IntegrationError:
        return Connection(status="NOT_CONFIGURED", unavailable=sorted(READ_TOOLS))
    async with operation() as (data, _, _auth):
        return status_view(data)


@router.post("/connect")
async def connect(response: Response):
    async with operation() as (data, vault, auth):
        if data.get("tokens") or data.get("revoking"):
            raise IntegrationError("DISCONNECT_FIRST", 409)
        throttle(data, "next_connect", 10)
        url, binding = await auth.begin(data)
        data.pop("error", None)
        vault.save(data)
        response.set_cookie(
            COOKIE,
            binding,
            max_age=600,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return {"authorization_url": url}


@router.get("/callback")
async def callback(request: Request):
    async with operation() as (data, vault, auth):
        query = request.query_params
        pending = data.get("pending", {})
        state = query.get("state", "")
        binding = request.cookies.get(COOKIE, "")
        if (
            len(query.getlist("state")) != 1
            or not state
            or not binding
            or not hmac.compare_digest(
                pending.get("state", "").encode(), state.encode()
            )
            or not hmac.compare_digest(
                pending.get("browser", "").encode(), binding.encode()
            )
            or pending.get("until", 0) < time.time()
        ):
            raise IntegrationError("INVALID_OAUTH_STATE", 400)
        del data["pending"]
        vault.save(data)
        if query.get("error"):
            data["error"] = "CONSENT_DECLINED"
        elif (
            query.getlist("iss") != [ISSUER]
            or len(query.getlist("code")) != 1
            or not query["code"]
            or len(query["code"]) > 8192
        ):
            raise IntegrationError("INVALID_CALLBACK", 400)
        else:
            await auth.exchange(
                data,
                {
                    "grant_type": "authorization_code",
                    "code": query["code"],
                    "redirect_uri": callback_uri(),
                    "code_verifier": pending["verifier"],
                },
            )
            vault.save(data)
            async with readonly_session(data["tokens"]["access_token"]) as broker:
                data["tools"] = sorted(broker.granted)
            data.pop("error", None)
        vault.save(data)
    response = RedirectResponse(
        "/settings/integrations",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.post("/disconnect", response_model=Connection)
async def disconnect():
    async with operation() as (data, vault, auth):
        await auth.revoke(data, vault.save)
        return status_view(data)


@router.post("/sync", response_model=Portfolio)
async def sync(db: Session = Depends(get_db)):
    async with operation() as (data, vault, auth):
        throttle(data, "next_sync", 30)
        token = await auth.access(data)
        vault.save(
            data
        )  # Persist a rotated refresh token before performing any more I/O.
        async with readonly_session(token) as broker:
            data["tools"] = sorted(broker.granted)
            data.pop("portfolio", None)
            vault.save(data)
            identities = dict(db.query(EGXSecurity.ticker, EGXSecurity.isin).all())
            result = await synchronize(broker, identities)
        data.update(portfolio=result.model_dump(mode="json"), error=None)
        vault.save(data)
        return result


@router.get("/portfolio", response_model=Portfolio)
async def portfolio():
    async with operation() as (data, vault, auth):
        cached = data.get("portfolio")
        if not cached or data.get("reauth") or data.get("revoking"):
            return Portfolio()
        # A remote revocation or a lost grant must also protect previously stored values.
        throttle(data, "next_view", 3)
        token = await auth.access(data)
        vault.save(data)
        async with readonly_session(token) as broker:
            if set(data.get("tools", [])) != set(broker.granted):
                data.pop("portfolio", None)
                data["tools"] = sorted(broker.granted)
                vault.save(data)
                raise IntegrationError("PERMISSIONS_CHANGED", 409)
        return Portfolio.model_validate(cached)
