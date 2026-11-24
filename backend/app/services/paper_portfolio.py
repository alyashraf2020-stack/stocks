"""Virtual ledger projections consumed by the original advanced risk engine."""

from decimal import Decimal

from app.schemas.risk import (
    Candidate,
    EquityPoint,
    PendingBuy,
    PortfolioSnapshot,
    RiskPosition,
)
from app.services.backtest_data import previous
from app.services.paper_execution import money
from app.services.portfolio_risk import ZERO, trade_costs
from app.services.risk_policy import calculate_size


def reserved(orders):
    return sum(
        (
            order.reservation
            for order in orders
            if order.open and order.request.side == "BUY"
        ),
        ZERO,
    )


def valuation(book):
    invested = sum((pos.cost for pos in book.positions.values()), ZERO)
    unsettled = sum((lot.amount for lot in book.proceeds), ZERO)
    marked = all(ticker in book.marks for ticker in book.positions)
    market_value = (
        sum((book.marks[t] * p.shares for t, p in book.positions.items()), ZERO)
        if marked
        else None
    )
    equity = money(book.settled_cash + unsettled + market_value) if marked else None
    return equity, market_value, money(invested), unsettled


def mark(book, day, bars, *, inception=False):
    book.marks = {key: bar.close for key, bar in bars.items() if bar}
    equity = valuation(book)[0]
    nav = money(equity / book.units) if equity is not None and book.units > 0 else None
    book.history = [entry for entry in book.history if entry["day"] != day.isoformat()]
    book.history.append(
        {
            "day": day.isoformat(),
            "equity": str(equity) if equity is not None else None,
            "nav": str(nav) if nav is not None else None,
            "exposed": bool(book.positions),
            "inception": inception,
        }
    )
    return equity


def portfolio_view(book, orders):
    equity, market, cost, unsettled = valuation(book)
    basis = book.history[-2]["nav"] if len(book.history) >= 2 else None
    nav = equity / book.units if equity is not None and book.units else None
    return {
        "settled_cash": book.settled_cash,
        "reserved_cash": reserved(orders),
        "available_cash": book.settled_cash - reserved(orders),
        "unsettled_cash": unsettled,
        "equity": equity,
        "invested_cost": cost,
        "realized": book.realized,
        "unrealized": market - cost if market is not None else None,
        "fees": book.fees,
        "taxes": book.taxes,
        "cursor": book.cursor,
        "history": book.history,
        "daily_return": nav / Decimal(basis) - 1
        if nav is not None and basis and Decimal(basis)
        else None,
        "total_return": nav - 1 if nav is not None else None,
        "gross_exposure": market / equity if market is not None and equity else None,
        "positions": [
            {
                "ticker": t,
                "shares": p.shares,
                "settled": p.settled,
                "cost": p.cost,
                "average_cost": money(p.cost / p.shares),
                "mark": book.marks.get(t),
                "stop": p.stop,
                "target": p.target,
                "opened": p.opened,
                "unrealized": money(book.marks[t] * p.shares - p.cost)
                if t in book.marks
                else None,
            }
            for t, p in sorted(book.positions.items())
        ],
    }


def paper_policy(policy, profile):
    return policy.model_copy(
        update={
            "commission_rate": profile.commission_rate + profile.charges_rate,
            "buy_tax_rate": profile.buy_tax_rate,
            "sell_tax_rate": profile.sell_tax_rate,
            "slippage_rate": max(
                policy.slippage_rate, profile.slippage_rate + profile.spread_rate / 2
            ),
        }
    )


def entry_size(
    book, orders, request, entry, turnover, policy, profile, sectors, sharia, now
):
    effective = paper_policy(policy, profile)
    fee_buffer = profile.fixed_fee + profile.minimum_commission
    equity = valuation(book)[0]
    earlier = previous(now.date())
    # End-of-day decisions use today's checked mark and the last actual session baseline.
    nav = equity / book.units if equity is not None and book.units else None
    snapshot = PortfolioSnapshot(
        as_of=now,
        equity=equity if equity and equity > 0 else None,
        settled_cash=book.settled_cash,
        adjusted_equity_now=money(nav) if nav and nav > 0 else None,
        adjusted_history=[
            EquityPoint(day=x["day"], equity=x["nav"])
            for x in book.history[-400:]
            if x["nav"] is not None and Decimal(x["nav"]) > 0
        ],
        positions=[
            RiskPosition(
                ticker=t,
                shares=p.shares,
                mark=book.marks.get(t),
                stop=p.stop,
                average_cost=money(p.cost / p.shares),
                sellable_shares=p.settled,
            )
            for t, p in book.positions.items()
        ],
        pending_buys=[
            PendingBuy(
                ticker=o.request.ticker,
                reserved_cash=o.reservation,
                notional=money(o.entry_cap * o.remaining),
                planned_risk=money(o.risk_unit * o.remaining),
            )
            for o in orders
            if o.open and o.request.side == "BUY"
        ],
    )
    if not request.stop < entry < request.target:
        return {"shares": None, "blockers": ["INVALID_ENTRY_RISK_GEOMETRY"]}, ZERO
    candidate = Candidate(
        ticker=request.ticker,
        entry=money(entry),
        stop=request.stop,
        target=request.target,
        average_turnover=money(turnover) if turnover is not None else None,
    )
    result = calculate_size(
        candidate,
        snapshot,
        sectors,
        effective,
        "PAPER",
        sharia,
        now,
        fee_buffer=fee_buffer,
        previous_session=earlier,
        initial_baseline=bool(
            0 < len(book.history) < 3 and book.history[0].get("inception")
        ),
    )
    return result, trade_costs(
        effective, candidate.entry, candidate.stop, candidate.target, fee_buffer
    )[1]
