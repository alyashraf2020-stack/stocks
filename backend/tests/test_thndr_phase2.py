import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from app.integrations.thndr_auth import (
    CALLBACK,
    ISSUER,
    METADATA,
    RESOURCE,
    RESOURCE_METADATA,
    SCOPE,
    Vault,
)
from app.integrations.thndr_mcp import READ_TOOLS
from app.main import app
from app.schemas.thndr import Quote
from app.services.quote_freshness import validate_quote
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

BASE = "/api/v1/integrations/thndr"
OWNER = "test-owner-gateway-" + "a" * 32
ACCESS = "SENSITIVE_TEST_ACCESS"
REFRESH = "SENSITIVE_TEST_REFRESH"
CODE = "SENSITIVE_TEST_AUTH_CODE"
NOW = datetime(2026, 11, 23, 10, tzinfo=timezone.utc)
ISIN = "EGS72081C010"


@pytest.fixture
def broker(monkeypatch, tmp_path):
    key = Fernet.generate_key()
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", OWNER)
    monkeypatch.setenv("THNDR_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("THNDR_PRIVATE_DIR", str(tmp_path))
    redirect = "https://egx.example" + CALLBACK
    monkeypatch.setenv("THNDR_REDIRECT_URI", redirect)
    mock = SimpleNamespace(
        grants=set(READ_TOOLS) | {"cancel_order", "send_trade_proposal"},
        calls=[],
        token_forms=[],
        revocations=[],
        scope=SCOPE,
        resource_status=200,
        registration_status=201,
        token_error=False,
        revoke_failure=False,
        granted_payload={
            "currency": "EGP",
            "available_cash": 0,
            "total_value": 1200,
            "positions": [
                {
                    "ticker": "AMES",
                    "isin": ISIN,
                    "exchange": "EGX",
                    "currency": "EGP",
                    "quantity": 8,
                    "average_purchase_price": 42,
                    "market_price": 50,
                    "source_timestamp": "2026-10-01T10:00:00Z",
                }
            ],
        },
    )
    auth_url, token_url, revoke_url, reg_url = (
        ISSUER + "/" + path for path in ("authorize", "token", "revoke", "register")
    )

    def handle(req):
        url = str(req.url)
        if url == RESOURCE_METADATA:
            return httpx.Response(
                200, json={"resource": RESOURCE, "authorization_servers": [ISSUER]}
            )
        if url == METADATA:
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "scopes_supported": [SCOPE, "thndr:write"],
                    "code_challenge_methods_supported": ["S256"],
                    "registration_endpoint": reg_url,
                    "token_endpoint": token_url,
                    "authorization_endpoint": auth_url,
                    "revocation_endpoint": revoke_url,
                },
            )
        if url == reg_url:
            reg = json.loads(req.content)
            assert (
                reg["scope"] == SCOPE
                and reg["client_name"] == "EGX AI Trading Assistant"
            )
            assert (
                reg["redirect_uris"] == [redirect]
                and reg["token_endpoint_auth_method"] == "none"
            )
            return httpx.Response(
                mock.registration_status, json={"client_id": "egx-own-registration"}
            )
        if url == token_url:
            fields = parse_qs(req.content.decode())
            mock.token_forms.append(fields)
            assert fields["client_id"] == ["egx-own-registration"] and fields[
                "resource"
            ] == [RESOURCE]
            if mock.token_error:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": ACCESS,
                    "refresh_token": REFRESH,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    "scope": mock.scope,
                },
            )
        if url == revoke_url:
            mock.revocations.append(parse_qs(req.content.decode())["token"][0])
            return httpx.Response(503 if mock.revoke_failure else 200)
        assert url == RESOURCE and req.headers["Authorization"] == "Bearer " + ACCESS
        if mock.resource_status == 0:
            raise httpx.ConnectError("offline")
        if mock.resource_status != 200:
            return httpx.Response(mock.resource_status, headers={"Retry-After": "9"})
        msg = json.loads(req.content)
        method = msg["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": msg["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Thndr fixture", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": name,
                        "description": "Fixture",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                    for name in sorted(mock.grants)
                ]
            }
        else:
            assert method == "tools/call"
            name = msg["params"]["name"]
            assert name in READ_TOOLS and name in mock.grants
            mock.calls.append(name)
            payload = {
                "check_eligibility": {"eligible_for_egx": True},
                "get_market_status": {"is_open": True},
                "get_portfolio_overview": mock.granted_payload,
                "get_watchlist": {"watchlist": ["AMES"]},
                "get_account_activities": {"activities": []},
                "get_orders": {
                    "orders": [
                        {"status": "CANCELLED", "symbol": "AMES"},
                        {"status": "OPEN", "symbol": "AMES"},
                    ]
                },
                "get_trading_stats": {"currency": "EGP", "realized_pnl": -4},
            }[name]
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": msg["id"], "result": result}
        )

    constructor = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: constructor(transport=httpx.MockTransport(handle), **kw),
    )
    with TestClient(
        app,
        base_url="https://egx.example",
        headers={"X-EGX-Gateway": OWNER},
        follow_redirects=False,
    ) as client:
        mock.client = client
        mock.store = tmp_path / "thndr.enc"

        def stored():
            return json.loads(Fernet(key).decrypt(mock.store.read_bytes()))

        mock.stored = stored
        yield mock


def start(b):
    response = b.client.post(BASE + "/connect")
    assert response.status_code == 200, response.text
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "Secure" in response.headers["set-cookie"]
    )
    return {
        k: v[0]
        for k, v in parse_qs(
            urlsplit(response.json()["authorization_url"]).query
        ).items()
    }


def finish(b, params):
    return b.client.get(
        CALLBACK
        + "?"
        + urlencode({"code": CODE, "iss": ISSUER, "state": params["state"]})
    )


def authorize(b):
    query = start(b)
    assert query["scope"] == SCOPE and query["code_challenge_method"] == "S256"
    assert finish(b, query).status_code == 303
    verifier = b.token_forms[0]["code_verifier"][0]
    assert (
        query["code_challenge"]
        == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return query


def test_authorize_discover_sync_revoke_no_secrets(broker, caplog):
    b = broker
    caplog.set_level(logging.DEBUG)
    q = authorize(b)
    status = b.client.get(BASE + "/status").json()
    assert status["permissions"] == [SCOPE] and set(status["available"]) == READ_TOOLS
    response = b.client.post(BASE + "/sync")
    assert response.status_code == 200, response.text
    p = response.json()
    assert p["account"]["eligible_for_egx"] is True
    assert (
        p["available_cash"] == 0
        and p["invested_amount"] is None
        and p["realized_pnl"] == -4
    )
    assert p["holdings"][0]["quote"]["freshness"] == "DELAYED"
    assert p["holdings"][0]["quote"]["eligible_for_proposal"] is False
    assert (
        p["transactions"] == []
        and len(p["open_orders"]) == 1
        and p["watchlist"] == ["AMES"]
    )
    assert p["last_sync"] and b.client.get(BASE + "/portfolio").json() == p
    assert set(b.calls) <= READ_TOOLS
    public = (
        response.text + json.dumps(status) + caplog.text + repr(b.store.read_bytes())
    )
    for secret in (
        CODE,
        ACCESS,
        REFRESH,
        q["state"],
        b.token_forms[0]["code_verifier"][0],
    ):
        assert secret not in public
    assert b.client.post(BASE + "/disconnect").json()["status"] == "DISCONNECTED"
    assert b.revocations == [REFRESH, ACCESS] and "portfolio" not in b.stored()
    assert b.client.get(BASE + "/portfolio").json()["total_value"] is None
    assert finish(b, q).status_code == 400


@pytest.mark.parametrize(
    "failure", ["wrong_state", "wrong_browser", "expired", "wrong_issuer"]
)
def test_invalid_callback_never_exchanges_code(broker, failure):
    q = start(broker)
    state, issuer = q["state"], ISSUER
    if failure == "wrong_state":
        state = "different"
    if failure == "wrong_browser":
        broker.client.cookies.clear()
    if failure == "expired":
        d = broker.stored()
        d["pending"]["until"] = 0
        Vault().save(d)
    if failure == "wrong_issuer":
        issuer = "https://untrusted.example"
    r = broker.client.get(
        CALLBACK, params={"state": state, "iss": issuer, "code": CODE}
    )
    assert r.status_code == 400 and not broker.token_forms


def test_refresh_and_invalid_grant(broker):
    b = broker
    authorize(b)
    data = b.stored()
    data["tokens"]["expires_at"] = 0
    Vault().save(data)
    assert b.client.post(BASE + "/sync").status_code == 200
    assert b.token_forms[-1]["grant_type"] == ["refresh_token"]
    data = b.stored()
    data["tokens"]["expires_at"] = 0
    Vault().save(data)
    b.token_error = True
    assert b.client.get(BASE + "/portfolio").status_code == 401
    assert b.client.get(BASE + "/status").json()["status"] == "RECONNECT_REQUIRED"
    assert "portfolio" not in b.stored()


def test_registration_failure_and_excess_scope(broker):
    b = broker
    b.registration_status = 403
    assert b.client.post(BASE + "/connect").json()["detail"] == "REGISTRATION_REFUSED"
    d = b.stored()
    d.pop("next_connect")
    Vault().save(d)
    b.registration_status = 201
    b.scope = "thndr:read thndr:write"
    assert finish(b, start(b)).status_code == 403
    assert b.revocations == [REFRESH, ACCESS] and not b.calls


def test_partial_grants_and_invalid_broker_fields(broker):
    b = broker
    b.grants = {"get_portfolio_overview", "get_watchlist", "send_trade_proposal"}
    b.granted_payload = {
        "currency": "EGP",
        "positions": [{"ticker": "AMES", "quantity": "bad"}],
    }
    authorize(b)
    p = b.client.post(BASE + "/sync").json()
    assert (
        p["available_cash"] is None
        and p["holdings"] is None
        and p["open_orders"] is None
    )
    assert p["watchlist"] == ["AMES"]
    assert p["issues"]["get_portfolio_overview"] == "INVALID_BROKER_RESPONSE"
    assert p["issues"]["get_orders"] == "MISSING_PERMISSION"
    assert set(b.calls) == {"get_portfolio_overview", "get_watchlist"}
    b.grants = {"get_watchlist"}
    assert b.client.get(BASE + "/portfolio").status_code == 409
    assert "portfolio" not in b.stored()


@pytest.mark.parametrize("status,expected", [(429, 429), (401, 401), (0, 503)])
def test_network_rate_limits_and_external_revocation(broker, status, expected):
    authorize(broker)
    broker.resource_status = status
    response = broker.client.post(BASE + "/sync")
    assert response.status_code == expected, response.text
    if status == 429:
        assert response.headers["Retry-After"] == "9"
        assert broker.client.post(BASE + "/sync").status_code == 429
    if status == 401:
        assert (
            broker.client.get(BASE + "/status").json()["status"] == "RECONNECT_REQUIRED"
        )


def test_failed_revocation_disables_cache_and_can_retry(broker):
    b = broker
    authorize(b)
    assert b.client.post(BASE + "/sync").status_code == 200
    b.revoke_failure = True
    assert b.client.post(BASE + "/disconnect").status_code == 502
    assert b.client.get(BASE + "/status").json()["status"] == "REVOCATION_PENDING"
    assert b.client.get(BASE + "/portfolio").json()["last_sync"] is None
    b.revoke_failure = False
    assert b.client.post(BASE + "/disconnect").json()["status"] == "DISCONNECTED"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "status"),
        ("POST", "connect"),
        ("GET", "callback"),
        ("GET", "portfolio"),
        ("POST", "sync"),
        ("POST", "disconnect"),
    ],
)
def test_owner_gateway_required(broker, method, path):
    r = broker.client.request(
        method, BASE + "/" + path, headers={"X-EGX-Gateway": "forged"}
    )
    assert r.status_code == 403 and not broker.calls and not broker.store.exists()


@pytest.mark.parametrize(
    "change,expected",
    [
        ({}, "REALTIME_VERIFIED"),
        ({"source_timestamp": None}, "UNKNOWN"),
        ({"source_timestamp": NOW - timedelta(minutes=10)}, "STALE"),
        ({"delay_class": "DELAYED"}, "DELAYED"),
        ({"delay_class": "MANUAL"}, "MANUAL"),
        ({"delay_class": "HISTORICAL"}, "HISTORICAL"),
        ({"instrument_id": "OTHER"}, "UNKNOWN"),
        ({"ticker": "OTHER"}, "UNKNOWN"),
        ({"exchange": "OTHER"}, "UNKNOWN"),
        ({"currency": "USD"}, "UNKNOWN"),
        ({"session_status": "CLOSED"}, "UNKNOWN"),
        ({"provider": "unentitled"}, "UNKNOWN"),
        ({"source_timestamp": NOW + timedelta(seconds=1)}, "UNKNOWN"),
    ],
)
def test_independent_quote_validation(change, expected):
    raw = dict(
        ticker="AMES",
        instrument_id=ISIN,
        exchange="EGX",
        currency="EGP",
        price=42,
        source_timestamp=NOW,
        retrieved_at=NOW,
        provider="licensed-fixture",
        session_status="OPEN",
        delay_class="REALTIME",
    )
    quote = Quote(**{**raw, **change})
    check = validate_quote(
        quote,
        ticker="AMES",
        instrument_id=ISIN,
        now=NOW,
        realtime_providers=frozenset({"licensed-fixture"}),
    )
    assert check.freshness == expected and check.eligible_for_proposal == (
        expected == "REALTIME_VERIFIED"
    )
