"""Deterministic completed-bar fills and exact virtual account postings."""

from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from app.schemas.paper_trading import Position, Settlement
from app.services.backtest_data import after
from app.services.portfolio_risk import ZERO, round_shares
from app.services.scanner_calendar import COVERAGE, hours

STEP = Decimal(".000001")
ONE = Decimal(1)
VERSION = "EGX_DAILY_EXECUTION_V1"


def money(value):
    return Decimal(value).quantize(STEP)


def grid(price, tick, rounding):
    return (price / tick).to_integral_value(rounding=rounding) * tick


def charges(order, raw_value, profile):
    def commission(value):
        if not value:
            return ZERO
        return profile.fixed_fee + max(
            profile.minimum_commission, profile.commission_rate * value
        )

    fee = commission(order.notional + raw_value) - commission(order.notional)
    tax_rate = (
        profile.buy_tax_rate if order.request.side == "BUY" else profile.sell_tax_rate
    )
    return money(fee + raw_value * profile.charges_rate), money(raw_value * tax_rate)


def reserve(order, profile):
    value = order.entry_cap * order.remaining
    fees, tax = charges(order, value, profile)
    return money(value + fees + tax)


def released(book, day):
    ready = [p.amount for p in book.proceeds if p.available and p.available <= day]
    book.proceeds = [p for p in book.proceeds if not p.available or p.available > day]
    book.settled_cash += sum(ready, ZERO)
    for pos in book.positions.values():
        pos.settled += sum(
            int(p.amount) for p in pos.unsettled if p.available and p.available <= day
        )
        pos.unsettled = [
            p for p in pos.unsettled if not p.available or p.available > day
        ]
    return sum(ready, ZERO)


def opening_order(order, bar):
    request = order.request
    if order.triggered or request.kind == "MARKET":
        return True
    if request.kind == "STOP":
        return bar.open <= request.trigger
    bound = request.limit or request.trigger
    return bar.open <= bound if request.side == "BUY" else bar.open >= bound


def raw_price(order, bar, profile):
    request = order.request
    opening = opening_order(order, bar)
    if request.kind == "STOP":
        if bar.low <= request.trigger or order.triggered:
            order.triggered = True
            return (bar.open, True) if opening else (request.trigger, False)
        return None
    if opening:
        return bar.open, True
    bound = request.limit or request.trigger
    if request.side == "BUY":
        factor = (1 + profile.spread_rate / 2) * (1 + profile.slippage_rate)
        return (bound / factor, False) if bar.low <= bound / factor else None
    factor = (1 - profile.spread_rate / 2) * (1 - profile.slippage_rate)
    return (bound / factor, False) if bar.high >= bound / factor else None


def modeled_price(order, bar, profile):
    if not bar.tick or not bar.lower_limit or not bar.upper_limit or not bar.volume:
        return None
    raw = raw_price(order, bar, profile)
    if raw is None:
        return None
    base, opening = raw
    buy = order.request.side == "BUY"
    sign = ONE if buy else -ONE
    reference = base * (ONE + sign * profile.spread_rate / 2)
    if opening and bar.opening_bid:
        reference = max(base, bar.opening_ask) if buy else min(base, bar.opening_bid)
    priced = grid(
        money(reference * (ONE + sign * profile.slippage_rate)),
        bar.tick,
        ROUND_CEILING if buy else ROUND_FLOOR,
    )
    priced = min(bar.high, max(bar.low, priced))
    if not bar.lower_limit <= priced <= bar.upper_limit:
        return None
    if buy and (
        priced > order.entry_cap
        or not order.request.stop < priced < order.request.target
    ):
        return None
    if order.request.limit and not (
        priced <= order.request.limit if buy else priced >= order.request.limit
    ):
        return None
    if order.request.kind == "TARGET" and priced < order.request.trigger:
        return None
    return priced, abs(priced - base)


def quantity_cap(bar, profile):
    return round_shares(Decimal(bar.volume) * profile.participation)


def apply_fill(
    book, order, bar, profile, quantity, price, friction, isin, *, opening=None
):
    if (
        not order.open
        or bar.day < order.eligible
        or not 0 < quantity <= order.remaining
    ):
        return None
    side, ticker = order.request.side, order.request.ticker
    value = money(price * quantity)
    fees, tax = charges(order, value, profile)
    clearing = after(bar.day, profile.settlement_sessions)
    pnl = None
    pos = book.positions.get(ticker)
    if side == "BUY":
        outlay = value + fees + tax
        if order.reservation < outlay or book.settled_cash < outlay:
            return None
        book.settled_cash -= outlay
        if not pos:
            pos = book.positions[ticker] = Position(
                isin=isin,
                cost=ZERO,
                stop=order.request.stop,
                target=order.request.target,
                opened=bar.day,
                strategy=str(order.evidence.get("strategy", "MANUAL")),
                protection_created=bar.available_at,
            )
        if pos.isin != isin:
            raise ValueError("POSITION_IDENTITY_CHANGED")
        pos.cost += outlay
        pos.unsettled.append(Settlement(available=clearing, amount=Decimal(quantity)))
    else:
        if not pos or pos.isin != isin or pos.settled < quantity or value <= fees + tax:
            return None
        basis = (
            pos.cost
            if quantity == pos.shares
            else money(pos.cost * quantity / pos.shares)
        )
        cash_proceeds = value - fees - tax
        pnl = cash_proceeds - basis
        book.realized += pnl
        pos.cost -= basis
        pos.settled -= quantity
        book.proceeds.append(Settlement(available=clearing, amount=cash_proceeds))
        if not pos.shares:
            del book.positions[ticker]
    book.fees += fees
    book.taxes += tax
    order.notional += value
    order.filled += quantity
    order.status = "PARTIALLY_FILLED" if order.remaining else "FILLED"
    order.reservation = (
        reserve(order, profile) if side == "BUY" and order.remaining else ZERO
    )
    return {
        "order_id": order.id,
        "ticker": ticker,
        "side": side,
        "shares": quantity,
        "price": str(price),
        "notional": str(value),
        "fees": str(fees),
        "tax": str(tax),
        "broker_commission": str(money(fees - value * profile.charges_rate)),
        "slippage": str(money(friction * quantity)),
        "realized": str(pnl) if pnl is not None else None,
        "trade_session": bar.day.isoformat(),
        "price_known_at": bar.available_at.isoformat(),
        "decision_session": order.decision_session.isoformat(),
        "created": order.created.isoformat(),
        "modeled_timing": "OPEN"
        if (opening if opening is not None else opening_order(order, bar))
        else "DAILY_RANGE",
        "settles": clearing.isoformat() if clearing else None,
        "holding_days": (bar.day - pos.opened).days if side == "SELL" else None,
        "reason": order.reason or "MANUAL",
        "evidence": order.evidence,
    }


def corporate_action(book, ticker, action):
    pos = book.positions.get(ticker)
    if not pos:
        return ZERO
    if action.kind == "OTHER":
        raise ValueError("UNMODELED_CORPORATE_ACTION")
    if action.kind == "DIVIDEND":
        # Approved per-share net cash and ex-date ownership are upstream inputs.
        cash = money(action.cash_per_share * pos.shares)
        eligible = action.payable_on
        while COVERAGE[0] <= eligible <= COVERAGE[1] and not isinstance(
            hours(eligible), tuple
        ):
            eligible += timedelta(days=1)
        if not COVERAGE[0] <= eligible <= COVERAGE[1]:
            eligible = None
        book.proceeds.append(Settlement(available=eligible, amount=cash))
        return cash
    ratio = action.ratio
    quantities = [
        Decimal(pos.settled) * ratio,
        *(lot.amount * ratio for lot in pos.unsettled),
    ]
    if any(value != value.to_integral_value() for value in quantities):
        raise ValueError("FRACTIONAL_CORPORATE_ACTION")
    pos.settled = int(quantities[0])
    for lot, quantity in zip(pos.unsettled, quantities[1:], strict=True):
        lot.amount = quantity
    pos.stop = money(pos.stop / ratio)
    pos.target = money(pos.target / ratio)
    if ticker in book.marks:
        book.marks[ticker] = money(book.marks[ticker] / ratio)
    return ZERO


def expires(order, day: date):
    if order.open and day > order.expires and not order.mandatory:
        order.status, order.reason, order.reservation = (
            "EXPIRED",
            "ORDER_WINDOW_ENDED",
            ZERO,
        )
