"""Thndr's OAuth-protected streamable HTTP transport. No generic tool proxy."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from app.integrations.thndr_auth import RESOURCE, IntegrationError, retry_seconds

READ_TOOLS = frozenset(
    {
        "check_eligibility",
        "get_portfolio_overview",
        "get_account_activities",
        "get_orders",
        "get_watchlist",
        "get_market_status",
        "get_assets_info",
        "get_trading_stats",
    }
)


class ReadSession:
    def __init__(self, session):
        self.session = session
        self.granted = {}

    async def discover(self):
        self.granted.clear()
        cursor = None
        seen = set()
        for _ in range(16):
            page = await self.session.list_tools(cursor=cursor)
            for tool in page.tools:
                if tool.name in READ_TOOLS:
                    self.granted[tool.name] = tool.inputSchema
            cursor = page.nextCursor
            if not cursor:
                return
            if cursor in seen:
                break
            seen.add(cursor)
        raise IntegrationError("INVALID_TOOL_CATALOG")

    async def read(self, name, arguments=None):
        if name not in READ_TOOLS or name not in self.granted:
            raise IntegrationError("MISSING_PERMISSION", 403)
        args = arguments or {}
        schema = self.granted[name]
        if (
            not set(schema.get("required", ())).issubset(args)
            or not args.keys() <= schema.get("properties", {}).keys()
        ):
            raise IntegrationError("UNSUPPORTED_TOOL_SCHEMA")
        result = await self.session.call_tool(name, arguments=args)
        if result.isError:
            raise IntegrationError("TOOL_UNAVAILABLE")
        payload = result.structuredContent
        if (
            payload is None
            and len(result.content) == 1
            and result.content[0].type == "text"
        ):
            try:
                payload = json.loads(result.content[0].text)
            except ValueError:
                pass
        if not isinstance(payload, (list, dict)):
            raise IntegrationError("INVALID_BROKER_RESPONSE")
        return payload


@asynccontextmanager
async def readonly_session(token):
    upstream_error = None

    async def observe(response):
        nonlocal upstream_error
        if response.status_code in (401, 403):
            upstream_error = IntegrationError(
                "RECONNECT_REQUIRED"
                if response.status_code == 401
                else "MISSING_PERMISSION",
                response.status_code,
            )
        if response.status_code == 429:
            upstream_error = IntegrationError(
                "RATE_LIMITED", 429, retry_seconds(response.headers.get("Retry-After"))
            )
        if upstream_error:
            raise upstream_error

    try:
        async with (
            asyncio.timeout(45),
            httpx.AsyncClient(
                headers={"Authorization": "Bearer " + token},
                timeout=12,
                follow_redirects=False,
                event_hooks={"response": [observe]},
            ) as http,
        ):
            async with streamable_http_client(
                RESOURCE, http_client=http, terminate_on_close=False
            ) as (rx, tx, _):
                async with ClientSession(
                    rx,
                    tx,
                    client_info=types.Implementation(
                        name="EGX AI Trading Assistant", version="0.2.0"
                    ),
                ) as client:
                    await client.initialize()
                    session = ReadSession(client)
                    await session.discover()
                    # Preserve domain errors across the SDK's task-group exception wrapping.
                    caught = None
                    try:
                        yield session
                    except IntegrationError as exc:
                        caught = exc
        if caught:
            raise caught
    except IntegrationError:
        raise
    except Exception:
        raise upstream_error or IntegrationError("MCP_UNAVAILABLE", 503) from None
