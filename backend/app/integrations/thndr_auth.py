"""Public-client OAuth with owner consent, S256 PKCE and encrypted local persistence."""

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from filelock import AsyncFileLock, Timeout
from pydantic import BaseModel, Field, ValidationError

from app.core.config import BACKEND_ROOT

RESOURCE = "https://mcp.thndr.app/mcp"
RESOURCE_METADATA = "https://mcp.thndr.app/.well-known/oauth-protected-resource/mcp"
ISSUER = "https://prod.thndr.app/krakend-mcp-server"
METADATA = (
    "https://prod.thndr.app/.well-known/oauth-authorization-server/krakend-mcp-server"
)
SCOPE = "thndr:read"
CALLBACK = "/api/v1/integrations/thndr/callback"


# Access logs can include single-use codes and OAuth state in the callback query.
# The MCP SDK can log complete inbound messages and its transport session ID.
class _PrivateCallbackFilter(logging.Filter):
    def filter(self, record):
        return CALLBACK not in record.getMessage()


for _logger in ("uvicorn.access", "httpx"):
    logging.getLogger(_logger).addFilter(_PrivateCallbackFilter())
logging.getLogger("mcp").addHandler(logging.NullHandler())
logging.getLogger("mcp").propagate = False


class IntegrationError(Exception):
    def __init__(self, code: str, status: int = 502, retry_after: int = 0):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


def retry_seconds(value):
    try:
        return min(3600, max(1, int(value)))
    except (TypeError, ValueError):
        return 60


class Vault:
    def __init__(self):
        try:
            self.cipher = Fernet(os.environ.get("THNDR_ENCRYPTION_KEY", ""))
        except (TypeError, ValueError):
            raise IntegrationError("NOT_CONFIGURED", 503) from None
        self.path = (
            Path(os.getenv("THNDR_PRIVATE_DIR", str(BACKEND_ROOT / "instance")))
            / "thndr.enc"
        )

    @asynccontextmanager
    async def locked(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            async with AsyncFileLock(str(self.path) + ".lock", timeout=2):
                try:
                    data = json.loads(self.cipher.decrypt(self.path.read_bytes()))
                except FileNotFoundError:
                    data = {}
                except (InvalidToken, ValueError):
                    raise IntegrationError("STORAGE_UNREADABLE", 503) from None
                yield data
        except Timeout:
            raise IntegrationError("BUSY", 429, 3) from None

    def save(self, data):
        blob = self.cipher.encrypt(json.dumps(data, allow_nan=False).encode())
        with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
            tmp = Path(stream.name)
            try:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.replace(tmp, self.path)
            finally:
                tmp.unlink(missing_ok=True)


def callback_uri():
    url = os.getenv("THNDR_REDIRECT_URI", "")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.path != CALLBACK
        or parts.query
        or parts.fragment
    ):
        raise IntegrationError("NOT_CONFIGURED", 503)
    return url


class Tokens(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: str
    expires_in: int = Field(gt=0)
    refresh_token: str | None = Field(default=None, min_length=1)
    scope: str | None = None


class ThndrOAuth:
    def __init__(self, client: httpx.AsyncClient):
        self.http = client

    async def request(self, method, url, *, empty=False, **kwargs):
        try:
            response = await self.http.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise IntegrationError("NETWORK_UNAVAILABLE", 503) from None
        if response.status_code == 429:
            raise IntegrationError(
                "RATE_LIMITED", 429, retry_seconds(response.headers.get("Retry-After"))
            )
        if not response.is_success:
            try:
                err = response.json().get("error")
            except (ValueError, AttributeError):
                err = None
            if err == "invalid_grant":
                raise IntegrationError("RECONNECT_REQUIRED", 401)
            raise IntegrationError(
                "REGISTRATION_REFUSED" if kwargs.get("json") else "BROKER_REJECTED"
            )
        if empty:
            return
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            raise IntegrationError("INVALID_BROKER_RESPONSE") from None

    async def metadata(self):
        resource = await self.request("GET", RESOURCE_METADATA)
        auth_servers = resource.get("authorization_servers")
        if (
            resource.get("resource") != RESOURCE
            or not isinstance(auth_servers, list)
            or ISSUER not in auth_servers
        ):
            raise IntegrationError("INVALID_METADATA")
        meta = await self.request("GET", METADATA)
        challenges = meta.get("code_challenge_methods_supported")
        scopes = meta.get("scopes_supported")
        if (
            meta.get("issuer") != ISSUER
            or not isinstance(challenges, list)
            or "S256" not in challenges
            or not isinstance(scopes, list)
            or SCOPE not in scopes
        ):
            raise IntegrationError("INVALID_METADATA")
        for field in (
            "authorization_endpoint",
            "token_endpoint",
            "revocation_endpoint",
            "registration_endpoint",
        ):
            url = meta.get(field)
            if not url and field == "registration_endpoint":
                continue
            if (
                not isinstance(url, str)
                or not url.startswith(ISSUER + "/")
                or "?" in url
                or "#" in url
                or any(char.isspace() for char in url)
            ):
                raise IntegrationError("INVALID_METADATA")
        return meta

    async def begin(self, data):
        redirect = callback_uri()
        meta = await self.metadata()
        if not data.get("client_id") or data.get("redirect") != redirect:
            if not meta.get("registration_endpoint"):
                raise IntegrationError("REGISTRATION_UNAVAILABLE", 409)
            registered = await self.request(
                "POST",
                meta["registration_endpoint"],
                json={
                    "client_name": "EGX AI Trading Assistant",
                    "redirect_uris": [redirect],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": SCOPE,
                },
            )
            cid = registered.get("client_id")
            if (
                not isinstance(cid, str)
                or not cid
                or registered.get("token_endpoint_auth_method", "none") != "none"
                or registered.get("redirect_uris", [redirect]) != [redirect]
            ):
                raise IntegrationError("INVALID_REGISTRATION")
            data.update(client_id=cid, redirect=redirect)
        state, verifier, browser = (secrets.token_urlsafe(48) for _ in range(3))
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        data["pending"] = dict(
            state=state, verifier=verifier, browser=browser, until=time.time() + 600
        )
        url = (
            meta["authorization_endpoint"]
            + "?"
            + urlencode(
                dict(
                    response_type="code",
                    client_id=data["client_id"],
                    redirect_uri=redirect,
                    scope=SCOPE,
                    resource=RESOURCE,
                    state=state,
                    code_challenge=challenge,
                    code_challenge_method="S256",
                )
            )
        )
        return url, browser

    async def exchange(self, data, form):
        meta = await self.metadata()
        body = await self.request(
            "POST",
            meta["token_endpoint"],
            data={**form, "client_id": data["client_id"], "resource": RESOURCE},
        )
        try:
            tokens = Tokens.model_validate(body)
        except ValidationError:
            raise IntegrationError("INVALID_TOKEN_RESPONSE") from None
        # An omitted scope inherits the requested scope under RFC 6749.
        if tokens.token_type.lower() != "bearer" or set(
            (tokens.scope if tokens.scope is not None else SCOPE).split()
        ) != {SCOPE}:
            # Revoke any unexpected grant before exposing or using it.
            data["tokens"] = {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
            }
            data["revoking"] = True
            raise IntegrationError("UNEXPECTED_GRANT", 403)
        old = data.get("tokens", {})
        data["tokens"] = dict(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token or old.get("refresh_token"),
            expires_at=time.time() + tokens.expires_in,
        )
        data.pop("reauth", None)

    async def access(self, data):
        token = data.get("tokens")
        if not token or data.get("revoking") or data.get("reauth"):
            raise IntegrationError("RECONNECT_REQUIRED", 401)
        if token["expires_at"] <= time.time() + 30:
            if not token.get("refresh_token"):
                raise IntegrationError("RECONNECT_REQUIRED", 401)
            await self.exchange(
                data,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": token["refresh_token"],
                },
            )
        return data["tokens"]["access_token"]

    async def revoke(self, data, save):
        token = data.get("tokens", {})
        data.pop("portfolio", None)
        data.pop("pending", None)
        data.pop("tools", None)
        data["revoking"] = True
        save(data)
        if token:
            meta = await self.metadata()
            for field in ("refresh_token", "access_token"):
                if token.get(field):
                    await self.request(
                        "POST",
                        meta["revocation_endpoint"],
                        empty=True,
                        data={
                            "token": token[field],
                            "token_type_hint": field,
                            "client_id": data["client_id"],
                        },
                    )
                    token.pop(field)
                    save(data)
        for key in ("tokens", "revoking", "reauth", "error", "cooldown"):
            data.pop(key, None)
        save(data)
