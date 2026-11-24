"""Conditional management of an existing position with settlement and fee checks."""

from decimal import Decimal

from app.services.portfolio_risk import (
    ONE,
    ZERO,
    fees_configured,
    position_risk,
    value_of,
)


def review_position(position, request, snapshot, summary, policy, proposed=None):
    quantity, mark, basis = position.shares, position.mark, position.average_cost
    value = value_of(position)
    sector = summary.get("candidate_sector")
    equity = snapshot.equity
    exposure = value / equity if value is not None and equity else None
    allocation = (
        max(ZERO, equity * policy.max_stock_allocation - value)
        if equity and value is not None
        else None
    )
    if allocation is not None:
        buys = snapshot.pending_buys
        if buys is None or any(p.notional is None for p in buys):
            allocation = None
        else:
            allocation = max(
                ZERO,
                allocation
                - sum((p.notional for p in buys if p.ticker == position.ticker), ZERO),
            )
    pnl = (mark - basis) * quantity if mark and basis and quantity else None
    before = position_risk(position, policy)
    result = {
        "ticker": position.ticker,
        "action": request.action,
        "current_value": value,
        "average_cost": basis,
        "unrealized_pnl": pnl,
        "unrealized_return": (mark - basis) / basis if mark and basis else None,
        "exposure_ratio": exposure,
        "remaining_allocation": allocation,
        "sector": sector,
        "risk_before": before,
        "risk_after": None,
        "remaining_cash": summary["available_cash"],
        "estimated_fees": None,
        "revised_average_cost": None,
        "shares": None,
        "unsettled_proceeds": None,
        "limitations": [],
        "executable": False,
    }
    missing = result["limitations"]
    if not summary["fresh"]:
        missing.append("CURRENT_SNAPSHOT")
    if request.action in {"HOLD", "WAIT"}:
        result.update(
            risk_after=before, estimated_fees=ZERO, revised_average_cost=basis
        )
    elif request.action == "ADD_TO_POSITION":
        if proposed and proposed.get("shares"):
            units = proposed["shares"]
            if request.shares and request.shares != units:
                missing.append("USE_BOUNDED_ADD_SIZE")
                return result
            average = (
                (basis * quantity + proposed["cash_required"]) / (quantity + units)
                if basis and quantity
                else None
            )
            result.update(
                shares=units,
                revised_average_cost=average,
                estimated_fees=proposed["estimated_fees"],
                risk_after=before + proposed["planned_risk"]
                if before is not None
                else None,
                remaining_cash=proposed["cash_after"],
            )
        else:
            missing.extend(
                proposed["blockers"] if proposed else ["NO_ELIGIBLE_ADD_SETUP"]
            )
    elif request.action == "MOVE_STOP_LOSS":
        if (
            not request.revised_stop
            or not mark
            or not position.stop
            or not position.stop < request.revised_stop < mark
        ):
            missing.append("RAISED_STOP_REQUIRED")
        else:
            result.update(
                risk_after=position_risk(position, policy, request.revised_stop),
                revised_average_cost=basis,
                estimated_fees=ZERO,
            )
    elif (
        quantity is None
        or mark is None
        or position.sellable_shares is None
        or not fees_configured(policy)
    ):
        missing.append("MARK_SETTLED_SHARES_OR_FEES_MISSING")
    else:
        units = (
            quantity if request.action == "FULL_EXIT" else Decimal(request.shares or 0)
        )
        if (
            units <= 0
            or units > position.sellable_shares
            or (units >= quantity and request.action != "FULL_EXIT")
        ):
            missing.append("SELL_SIZE_OR_SETTLEMENT_LIMIT")
            return result
        gross = units * mark * (ONE - policy.slippage_rate)
        fee = gross * (policy.commission_rate + policy.sell_tax_rate)
        remaining = quantity - units
        result.update(
            shares=units,
            estimated_fees=fee,
            unsettled_proceeds=gross - fee,
            revised_average_cost=basis if remaining else None,
            risk_after=before * remaining / quantity
            if before is not None
            else ZERO
            if not remaining
            else None,
        )
    return result
