"""Normalize known structured fields. Unknown broker shapes stay unavailable."""

from datetime import datetime, timezone

from pydantic import ValidationError

from app.integrations.thndr_auth import IntegrationError
from app.schemas.thndr import AccountInfo, AccountItem, Holding, Portfolio, Quote
from app.services.quote_freshness import validate_quote


def pick(obj, *keys):
    for key in keys:
        if key in obj and obj[key] is not None:
            if isinstance(obj[key], bool):
                raise ValueError("unexpected boolean")
            return obj[key]
    return None


def unpack(payload):
    if isinstance(payload, dict):
        return payload.get("data", payload)
    return payload


def rows(payload, *keys):
    records = pick(payload, *keys) if isinstance(payload, dict) else payload
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("unrecognized list")
    return records


def normalize_quote(raw, ticker, identities, session):
    price = pick(raw, "current_price", "market_price", "price")
    if price is None:
        return None
    now = datetime.now(timezone.utc)
    quote = Quote(
        ticker=raw.get("ticker", raw.get("symbol")),
        instrument_id=raw.get("isin") or "",
        exchange=raw.get("exchange") or "",
        currency=raw.get("currency") or "",
        price=price,
        source_timestamp=pick(raw, "price_timestamp", "source_timestamp"),
        retrieved_at=now,
        provider="Thndr MCP",
        delay_class="DELAYED",
        session_status=session,
    )
    return validate_quote(
        quote, ticker=ticker, instrument_id=identities.get(ticker), now=now
    )


def overview(payload, identities, session):
    if not isinstance(payload, dict) or payload.get("currency") != "EGP":
        raise ValueError("unverified account currency")
    fields = {
        key: pick(payload, key, alias)
        for key, alias in [
            ("available_cash", "cash_balance"),
            ("total_value", "portfolio_value"),
            ("invested_amount", "invested_capital"),
            ("realized_pnl", "realized_profit_loss"),
            ("unrealized_pnl", "unrealized_profit_loss"),
        ]
    }
    positions = pick(payload, "holdings", "positions", "stocks")
    if isinstance(positions, dict):
        positions = positions.get("stocks")
    if positions is None and all(v is None for v in fields.values()):
        raise ValueError("unknown portfolio shape")
    holdings = None
    if positions is not None:
        holdings = []
        for raw in rows(positions):
            ticker = pick(raw, "ticker", "symbol")
            try:
                quote = normalize_quote(raw, ticker, identities, session)
            except (ValueError, TypeError):
                quote = None
            # Do not express another currency in EGP.
            egp = raw.get("currency", payload["currency"]) == "EGP"
            holdings.append(
                Holding(
                    ticker=ticker,
                    instrument_id=raw.get("isin"),
                    quantity=pick(raw, "quantity", "shares"),
                    average_price=pick(raw, "average_price", "average_purchase_price")
                    if egp
                    else None,
                    market_value=pick(raw, "market_value", "valuation")
                    if egp
                    else None,
                    unrealized_pnl=pick(raw, "unrealized_pnl", "unrealized_profit_loss")
                    if egp
                    else None,
                    quote=quote,
                )
            )
    return Portfolio(**fields, holdings=holdings, currency="EGP", market_status=session)


async def synchronize(session, identities):
    issues = {}

    async def fetch(name, convert, args=None):
        if name not in session.granted:
            issues[name] = "MISSING_PERMISSION"
            return None
        try:
            return convert(unpack(await session.read(name, args)))
        except IntegrationError as exc:
            if exc.code in {
                "RATE_LIMITED",
                "RECONNECT_REQUIRED",
                "NETWORK_UNAVAILABLE",
                "MCP_UNAVAILABLE",
            }:
                raise
            issues[name] = exc.code
        except (ValueError, TypeError, AttributeError, KeyError, ValidationError):
            issues[name] = "INVALID_BROKER_RESPONSE"
        return None

    def market(payload):
        value = payload.get("status", payload.get("market_status"))
        if isinstance(value, str) and value.upper() in {"OPEN", "CLOSED", "HALTED"}:
            return value.upper()
        if type(payload.get("is_open")) is bool:
            return "OPEN" if payload["is_open"] else "CLOSED"
        raise ValueError("unknown market status")

    market_status = await fetch("get_market_status", market) or "UNKNOWN"
    portfolio = await fetch(
        "get_portfolio_overview", lambda data: overview(data, identities, market_status)
    )
    result = portfolio or Portfolio(market_status=market_status)

    def account_items(data, key):
        result = []
        for raw in rows(data, key):
            status = pick(raw, "status", "order_status")
            if key == "orders":
                if not isinstance(status, str):
                    raise ValueError("unknown order status")
                if status.upper() in {
                    "FILLED",
                    "CANCELLED",
                    "CANCELED",
                    "EXPIRED",
                    "REJECTED",
                    "COMPLETED",
                }:
                    continue
                if status.upper() not in {
                    "OPEN",
                    "PENDING",
                    "PARTIALLY_FILLED",
                    "NEW",
                    "ACCEPTED",
                }:
                    raise ValueError("unknown order status")
            result.append(
                AccountItem(
                    kind=pick(raw, "type", "side"),
                    ticker=pick(raw, "ticker", "symbol"),
                    timestamp=pick(raw, "timestamp", "created_at"),
                    status=status,
                    amount=pick(raw, "amount")
                    if raw.get("currency") == "EGP"
                    else None,
                    quantity=pick(raw, "quantity"),
                )
            )
        return result

    def account_info(data):
        fields = (
            "registration_status",
            "eligible_for_egx",
            "deposits_enabled",
            "withdrawals_enabled",
        )
        return AccountInfo.model_validate(
            {field: data[field] for field in fields if field in data}, strict=True
        )

    result.account = await fetch("check_eligibility", account_info)
    result.transactions = await fetch(
        "get_account_activities", lambda data: account_items(data, "activities")
    )
    result.open_orders = await fetch(
        "get_orders", lambda data: account_items(data, "orders")
    )

    def watchlist(data):
        symbols = [
            item if isinstance(item, str) else pick(item, "ticker", "symbol")
            for item in rows(data, "watchlist", "items")
        ]
        return Portfolio(watchlist=symbols).watchlist

    result.watchlist = await fetch("get_watchlist", watchlist)

    if result.realized_pnl is None and "get_trading_stats" in session.granted:

        def realized(data):
            if data.get("currency") != "EGP":
                raise ValueError("unverified currency")
            return Portfolio(
                realized_pnl=pick(data, "realized_pnl", "realized_profit_loss")
            ).realized_pnl

        result.realized_pnl = await fetch("get_trading_stats", realized)

    if result.holdings and "get_assets_info" in session.granted:
        props = session.granted["get_assets_info"].get("properties", {})
        # Use only documented-by-discovery batch inputs and match results by identity.
        tickers = [h.ticker for h in result.holdings if h.quote is None]
        if tickers and "tickers" in props and props["tickers"].get("type") == "array":

            def quotes(payload):
                by_ticker = {}
                for raw in rows(payload, "assets", "items"):
                    ticker = pick(raw, "ticker", "symbol")
                    if ticker in tickers:
                        by_ticker[ticker] = normalize_quote(
                            raw, ticker, identities, market_status
                        )
                return by_ticker

            latest = await fetch("get_assets_info", quotes, {"tickers": tickers})
            for h in result.holdings:
                if h.quote is None and latest:
                    h.quote = latest.get(h.ticker)
        elif tickers:
            issues["get_assets_info"] = "UNSUPPORTED_TOOL_SCHEMA"

    result.issues = issues
    if (
        all(
            value is None
            for value in (
                portfolio,
                result.account,
                result.transactions,
                result.open_orders,
                result.watchlist,
                result.realized_pnl,
            )
        )
        and market_status == "UNKNOWN"
    ):
        raise IntegrationError("NO_USABLE_READS", 409)
    result.last_sync = datetime.now(timezone.utc)
    return result
