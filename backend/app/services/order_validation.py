"""Price and account checks for human review. These functions never call a broker."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.services.portfolio_risk import ZERO, fees_configured
from app.services.quote_freshness import validate_quote
from app.services.risk_policy import entry_blocks

BUY = {"BUY", "ADD"}


def amount(value):
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)


def check_price(quote, security, calendar, now, settings, entitled=frozenset()):
    if not quote:
        return "QUOTE_UNAVAILABLE"
    checked = validate_quote(
        quote,
        ticker=security.ticker,
        instrument_id=security.isin,
        realtime_providers=entitled,
        now=now,
        max_age=timedelta(seconds=settings.max_quote_age),
    )
    if checked.validation_status == "INVALID":
        return "QUOTE_IDENTITY_INVALID"
    if checked.freshness != "REALTIME_VERIFIED":
        return "QUOTE_" + checked.freshness
    if (
        not calendar.get("live_verified")
        or calendar["session_status"] != "OPEN"
        or quote.session_status != "OPEN"
    ):
        return "SESSION_NOT_AUTHORIZED"
    return None


def account_limits(request, snapshot, position, policy, sharia, size, price):
    if request.intent in BUY:
        blockers = entry_blocks(policy, sharia, advanced_supported=True)
        if request.intent == "ADD" and (not position or not position.shares):
            blockers.append("EXISTING_POSITION_REQUIRED")
        if request.intent == "BUY" and position and position.shares:
            blockers.append("USE_ADD_REVIEW")
        cash = [snapshot.settled_cash, snapshot.buying_power] if snapshot else []
        if not cash or any(v is None for v in cash):
            blockers.append("SETTLED_CASH_UNVERIFIED")
        if (
            not snapshot
            or snapshot.pending_buys is None
            or any(o.reserved_cash is None for o in snapshot.pending_buys)
        ):
            blockers.append("RESERVATIONS_UNVERIFIED")
        if (
            snapshot
            and cash
            and all(v is not None for v in cash)
            and request.shares
            and price
        ):
            reserved = sum(
                (o.reserved_cash or ZERO for o in snapshot.pending_buys or []), ZERO
            )
            free = min(cash[1], max(ZERO, cash[0] - reserved))
            if request.shares * price > free:
                blockers.append("INSUFFICIENT_CASH")
        if not size or not size.get("shares"):
            blockers.extend(size["blockers"] if size else ["SIZE_UNAVAILABLE"])
        elif request.shares and request.shares > size["shares"]:
            blockers.append("SIZE_EXCEEDS_RISK_LIMIT")
        return sorted(set(blockers))
    if not position or position.shares is None or position.sellable_shares is None:
        return ["SELLABLE_SHARES_UNKNOWN"]
    if request.shares and request.shares > position.sellable_shares:
        return ["INSUFFICIENT_SELLABLE_SHARES"]
    if request.intent == "FULL_EXIT" and position.sellable_shares != position.shares:
        return ["FULL_EXIT_SETTLEMENT_UNAVAILABLE"]
    if (
        request.intent == "FULL_EXIT"
        and request.shares is not None
        and request.shares != position.shares
    ):
        return ["FULL_EXIT_QUANTITY_MISMATCH"]
    if (
        request.intent in {"PARTIAL_SELL", "TAKE_PROFIT"}
        and request.shares is not None
        and request.shares >= position.shares
    ):
        return ["PARTIAL_EXIT_QUANTITY_REQUIRED"]
    return []


def estimate(policy, side, price, shares):
    if not price or not shares:
        return {"value": None, "commission": None, "tax": None, "required_cash": None}
    value = amount(price * shares)
    commission = (
        amount(value * policy.commission_rate) if fees_configured(policy) else None
    )
    tax = (
        amount(value * (policy.buy_tax_rate if side == "BUY" else policy.sell_tax_rate))
        if commission is not None
        else None
    )
    return {
        "value": value,
        "commission": commission,
        "tax": tax,
        "required_cash": value + commission + tax
        if side == "BUY" and commission is not None
        else None,
    }


def price_within_review(side, original, observed, settings):
    if original is None or observed is None or original <= 0:
        return False
    difference = observed - original if side == "BUY" else original - observed
    return difference <= original * Decimal(settings.max_adverse_move_bps) / 10000
