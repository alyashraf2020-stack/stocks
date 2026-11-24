"""Independent, source-aware portfolio risk calculations in EGP."""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_FLOOR, Decimal

from app.schemas.risk import PendingBuy, PortfolioSnapshot, RiskPosition
from app.schemas.thndr import Quote
from app.services.egx_calendar import CAIRO_TZ, get_expected_latest_completed_session
from app.services.quote_freshness import validate_quote

ZERO = Decimal(0)
ONE = Decimal(1)


def dec(value):
    return Decimal(str(value)) if value is not None else None


def broker_amount(value, *, positive=False):
    amount = dec(value)
    if amount is None or not ZERO <= amount <= Decimal("1e14"):
        return None
    amount = amount.quantize(Decimal(".000001"))
    return amount if amount or not positive else None


def known_sum(values):
    return None if any(value is None for value in values) else sum(values, ZERO)


def round_shares(value):
    return max(0, int(value.to_integral_value(rounding=ROUND_FLOOR)))


def value_of(position):
    if position.mark is not None and position.shares is not None:
        return position.mark * position.shares
    return position.reported_value


def fees_configured(policy):
    return all(
        value is not None
        for value in (policy.commission_rate, policy.buy_tax_rate, policy.sell_tax_rate)
    )


def trade_costs(policy, entry, stop, target, fee_buffer=ZERO):
    entry_fill = entry * (ONE + policy.slippage_rate)
    stop_fill = stop * (ONE - policy.slippage_rate) * (ONE - policy.stop_gap_rate)
    target_fill = target * (ONE - policy.slippage_rate)
    buy_fee = entry_fill * (policy.commission_rate + policy.buy_tax_rate) + fee_buffer
    sell_rate = policy.commission_rate + policy.sell_tax_rate
    cash_cost = entry_fill + buy_fee
    stop_net = stop_fill * (ONE - sell_rate) - fee_buffer
    target_net = target_fill * (ONE - sell_rate) - fee_buffer
    return cash_cost, cash_cost - stop_net, target_net - cash_cost, buy_fee


def position_risk(position, policy, stop=None, fee_buffer=ZERO):
    stop = position.stop if stop is None else stop
    if (
        not fees_configured(policy)
        or position.mark is None
        or position.shares is None
        or stop is None
    ):
        return None
    exit_fill = stop * (ONE - policy.slippage_rate) * (ONE - policy.stop_gap_rate)
    exit_net = exit_fill * (ONE - policy.commission_rate - policy.sell_tax_rate) - fee_buffer
    return max(ZERO, position.mark - exit_net) * position.shares


def history_metrics(snapshot, now, *, previous_session=None, initial_baseline=False):
    if (
        snapshot.adjusted_equity_now is None
        or not snapshot.adjusted_history
        or snapshot.as_of is None
    ):
        return None, None
    local = now.astimezone(CAIRO_TZ)
    previous = previous_session or get_expected_latest_completed_session(
        local.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    expected = max(previous, local.date()) if previous_session else get_expected_latest_completed_session(local)
    values = {entry.day: entry.equity for entry in snapshot.adjusted_history}
    if (
        snapshot.as_of > now
        or snapshot.as_of.astimezone(CAIRO_TZ).date() != local.date()
        or max(values) > expected
    ):
        return None, None
    base = values.get(previous)
    if not base and initial_baseline and len(values) == 1:
        # A newly initialized virtual account has a known opening NAV today.
        base = values.get(local.date())
    current = snapshot.adjusted_equity_now
    loss = max(ZERO, (base - current) / base) if base else None
    peak = max(values.values()) if (len(values) >= 2 or initial_baseline) and base is not None else None
    drawdown = max(ZERO, (peak - current) / peak) if peak else None
    return loss, drawdown


def summarize(snapshot, sectors, policy, source, now=None, *, fee_buffer=ZERO, previous_session=None, initial_baseline=False):
    now = now or datetime.now(timezone.utc)
    equity = snapshot.equity
    items = snapshot.positions
    stock = {p.ticker: value_of(p) for p in items or []}
    marks_known = items is not None and all(
        p.mark is not None and p.shares is not None for p in items
    )
    total = known_sum(list(stock.values())) if items is not None else None
    groups = {}
    for ticker, value in stock.items():
        group = sectors.get(ticker)
        if group is not None and value is not None:
            groups[group] = groups.get(group, ZERO) + value
    sector_known = items is not None and all(
        sectors.get(ticker) and value is not None for ticker, value in stock.items()
    )
    risks = [position_risk(p, policy, fee_buffer=fee_buffer) for p in items or []]
    risk = known_sum(risks) if items is not None else None
    pending = snapshot.pending_buys
    reserve = (
        known_sum([p.reserved_cash for p in pending]) if pending is not None else None
    )
    free_cash = (
        max(ZERO, snapshot.settled_cash - reserve)
        if snapshot.settled_cash is not None and reserve is not None
        else None
    )
    if free_cash is not None and snapshot.buying_power is not None:
        free_cash = min(free_cash, snapshot.buying_power)
    pending_risk = (
        known_sum([p.planned_risk for p in pending]) if pending is not None else None
    )
    loss, drawdown = history_metrics(snapshot, now, previous_session=previous_session, initial_baseline=initial_baseline)
    fresh = snapshot.as_of is not None and timedelta(
        0
    ) <= now - snapshot.as_of <= timedelta(minutes=policy.max_snapshot_minutes)
    budget = (
        max(ZERO, equity * policy.max_aggregate_risk - risk - pending_risk)
        if equity and risk is not None and pending_risk is not None
        else None
    )
    missing = [
        name
        for name, present in (
            ("EQUITY", equity is not None),
            ("SETTLED_CASH_AND_RESERVATIONS", free_cash is not None),
            ("POSITION_MARKS", marks_known),
            ("SECTOR_MAPPING", sector_known),
            ("PLANNED_OPEN_RISK", risk is not None),
            ("PENDING_RISK", pending_risk is not None),
            ("DAILY_LOSS_HISTORY", loss is not None),
            ("DRAWDOWN_HISTORY", drawdown is not None),
            ("CURRENT_SNAPSHOT", fresh),
            ("COST_CONFIGURATION", fees_configured(policy)),
        )
        if not present
    ]
    stopped_out = [
        p.ticker for p in items or [] if p.mark and p.stop and p.mark <= p.stop
    ]
    if stopped_out:
        missing.append("POSITION_STOP_BREACHED")
    if equity and snapshot.settled_cash is not None and snapshot.settled_cash > equity:
        missing.append("INCONSISTENT_EQUITY")
    stock_breaches = [
        ticker
        for ticker, value in stock.items()
        if equity and value is not None and value > equity * policy.max_stock_allocation
    ]
    sector_breaches = [
        sector
        for sector, value in groups.items()
        if equity and value > equity * policy.max_sector_exposure
    ]
    concentrations = {
        t: val / equity if equity and val is not None else None
        for t, val in stock.items()
    }
    return {
        "source": source,
        "as_of": snapshot.as_of,
        "fresh": fresh,
        "equity": equity,
        "total_exposure": total,
        "total_exposure_ratio": total / equity
        if total is not None and equity
        else None,
        "settled_cash": snapshot.settled_cash,
        "cash_ratio": snapshot.settled_cash / equity
        if snapshot.settled_cash is not None and equity
        else None,
        "available_cash": free_cash,
        "reported_buying_power": snapshot.buying_power,
        "reserved_cash": reserve,
        "stock_values": stock,
        "sector_values": groups,
        "stock_concentration": concentrations,
        "sector_concentration": {s: v / equity for s, v in groups.items()}
        if equity
        else {},
        "sector_count": len(groups) if sector_known else None,
        "position_count": len(stock) if items is not None else None,
        "largest_stock_ratio": max(concentrations.values(), default=ZERO)
        if equity and total is not None
        else None,
        "aggregate_position_risk": risk,
        "pending_position_risk": pending_risk,
        "available_risk_budget": budget,
        "daily_loss_ratio": loss,
        "drawdown_ratio": drawdown,
        "stock_breaches": stock_breaches,
        "sector_breaches": sector_breaches,
        "stop_breaches": stopped_out,
        "missing": missing,
    }


def brokerage_snapshot(portfolio, securities, now=None):
    """An available-cash snapshot alone cannot establish settlement or open stop risk."""
    positions = None
    if portfolio.holdings is not None:
        positions = []
        counts = {}
        for holding in portfolio.holdings:
            counts[holding.ticker] = counts.get(holding.ticker, 0) + 1
        if all(count == 1 for count in counts.values()):
            for holding in portfolio.holdings:
                match = securities.get(holding.ticker)
                identity = bool(
                    match and match.isin and holding.instrument_id == match.isin
                )
                checked = None
                if identity and holding.quote:
                    quote = Quote.model_validate(
                        holding.quote.model_dump(include=set(Quote.model_fields))
                    )
                    checked = validate_quote(
                        quote, ticker=holding.ticker, instrument_id=match.isin, now=now
                    )
                positions.append(
                    RiskPosition(
                        ticker=holding.ticker,
                        shares=broker_amount(holding.quantity, positive=True)
                        if identity
                        else None,
                        mark=broker_amount(checked.price, positive=True)
                        if checked and checked.freshness == "REALTIME_VERIFIED"
                        else None,
                        reported_value=broker_amount(holding.market_value)
                        if identity
                        else None,
                        average_cost=broker_amount(holding.average_price, positive=True)
                        if identity
                        else None,
                    )
                )
        else:
            positions = None
    orders = None
    if portfolio.open_orders is not None and all(
        order.ticker and order.kind and order.kind.upper() in {"BUY", "SELL"}
        for order in portfolio.open_orders
    ):
        orders = [
            PendingBuy(ticker=order.ticker)
            for order in portfolio.open_orders
            if order.kind.upper() == "BUY"
        ]
    return PortfolioSnapshot(
        as_of=portfolio.last_sync,
        equity=broker_amount(portfolio.total_value, positive=True),
        buying_power=broker_amount(portfolio.available_cash),
        positions=positions,
        pending_buys=orders,
    )
