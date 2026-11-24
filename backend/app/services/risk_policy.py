from sqlalchemy.dialects.sqlite import insert

from app.models.risk_settings import RiskSettings
from app.schemas.risk import RiskPolicy
from app.services.portfolio_risk import ZERO, position_risk, summarize, trade_costs
from app.services.risk_manager import RiskManager


def load_policy(db):
    row = db.get(RiskSettings, 1)
    return RiskPolicy.model_validate(row.policy) if row else RiskPolicy()


def save_policy(db, settings):
    payload = settings.model_dump(mode="json")
    if db.get_bind().dialect.name == "sqlite":
        statement = insert(RiskSettings).values(id=1, policy=payload)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["id"], set_={"policy": payload}
            )
        )
    else:
        db.merge(RiskSettings(id=1, policy=payload))
    db.commit()


def entry_blocks(policy, sharia_status, *, advanced_supported):
    reasons = []
    if policy.kill_switch:
        reasons.append("KILL_SWITCH")
    if policy.islamic_mode and sharia_status != "COMPLIANT":
        reasons.append("SHARIA_" + (sharia_status or "UNVERIFIED"))
    if policy.advanced_required and not advanced_supported:
        reasons.append("USE_PORTFOLIO_REVIEW")
    return reasons


def calculate_size(
    candidate, snapshot, sectors, policy, source, sharia_status, now=None
):
    portfolio = summarize(snapshot, sectors, policy, source, now)
    blockers = entry_blocks(policy, sharia_status, advanced_supported=True) + list(
        portfolio["missing"]
    )
    result = {
        "shares": None,
        "blockers": blockers,
        "portfolio": portfolio,
        "executable": False,
        "estimated_fees": None,
        "reward_to_risk": None,
        "planned_risk": None,
        "cash_after": None,
    }
    sector = sectors.get(candidate.ticker)
    if sector is None:
        blockers.append("CANDIDATE_SECTOR_UNKNOWN")
    if candidate.average_turnover is None:
        blockers.append("TURNOVER_UNKNOWN")
    elif candidate.average_turnover < policy.min_daily_turnover:
        blockers.append("MINIMUM_LIQUIDITY")
    if (
        portfolio["daily_loss_ratio"] is not None
        and portfolio["daily_loss_ratio"] >= policy.max_daily_loss
    ):
        blockers.append("DAILY_LOSS_LIMIT")
    if (
        portfolio["drawdown_ratio"] is not None
        and portfolio["drawdown_ratio"] >= policy.max_drawdown
    ):
        blockers.append("DRAWDOWN_LIMIT")
    pending = snapshot.pending_buys or []
    if any(p.notional is None or sectors.get(p.ticker) is None for p in pending):
        blockers.append("PENDING_EXPOSURE_UNKNOWN")
    if portfolio["stock_breaches"] or portfolio["sector_breaches"]:
        blockers.append("EXISTING_CONCENTRATION_BREACH")
    if blockers:
        return result

    equity = snapshot.equity
    cash_cost, unit_risk, unit_reward, fee = trade_costs(
        policy, candidate.entry, candidate.stop, candidate.target
    )
    result["reward_to_risk"] = unit_reward / unit_risk
    if result["reward_to_risk"] < policy.min_reward_to_risk:
        blockers.append("MINIMUM_REWARD_TO_RISK")
        return result
    pending_value = sum((p.notional for p in pending), ZERO)
    pending_sector = sum(
        (p.notional for p in pending if sectors[p.ticker] == sector), ZERO
    )
    pending_stock = sum(
        (p.notional for p in pending if p.ticker == candidate.ticker), ZERO
    )
    owned = {p.ticker for p in snapshot.positions} | {p.ticker for p in pending}
    existing = next(
        (p for p in snapshot.positions if p.ticker == candidate.ticker), None
    )
    if candidate.ticker not in owned and len(owned) >= policy.max_open_positions:
        blockers.append("OPEN_POSITIONS_LIMIT")
        return result

    # Charge a stock top-up for the existing stake's risk at its current stop.
    existing_risk = position_risk(existing, policy) if existing else ZERO
    pending_same_risk = sum(
        (p.planned_risk for p in pending if p.ticker == candidate.ticker), ZERO
    )
    limits = {
        "TRADE_RISK": (
            equity * policy.max_trade_risk - existing_risk - pending_same_risk
        )
        / unit_risk,
        "STOCK_ALLOCATION": (
            equity * policy.max_stock_allocation
            - portfolio["stock_values"].get(candidate.ticker, ZERO)
            - pending_stock
        )
        / cash_cost,
        "SECTOR_ALLOCATION": (
            equity * policy.max_sector_exposure
            - portfolio["sector_values"].get(sector, ZERO)
            - pending_sector
        )
        / cash_cost,
        "TOTAL_ALLOCATION": (
            equity * policy.max_total_exposure
            - portfolio["total_exposure"]
            - pending_value
        )
        / cash_cost,
        "PORTFOLIO_RISK": portfolio["available_risk_budget"] / unit_risk,
        "BUYING_POWER": portfolio["available_cash"] / cash_cost,
    }
    shares = RiskManager.bounded_shares(limits)
    result.update(
        shares=shares,
        estimated_fees=fee * shares,
        planned_risk=unit_risk * shares,
        cash_after=portfolio["available_cash"] - cash_cost * shares,
        cash_required=cash_cost * shares,
        limiting_rule=min(limits, key=limits.get),
    )
    if not shares:
        blockers.append(result["limiting_rule"])
    return result


def apply_analysis_policy(db, security, analysis):
    """Overlay owner limits after strategy evaluation and before OpenAI or ranking."""
    from app.services.sharia_filter import status_for

    policy = load_policy(db)
    screening = status_for(db, security) if policy.islamic_mode else None
    if screening:
        analysis.sharia_status = screening["status"]
    reasons = entry_blocks(policy, analysis.sharia_status, advanced_supported=False)
    add_on = analysis.position and (
        analysis.position.action == "ADD_TO_POSITION"
        or "ADD_TO_POSITION" in analysis.position.scenario_actions
    )
    if add_on and "USE_PORTFOLIO_REVIEW" not in reasons:
        reasons.append("USE_PORTFOLIO_REVIEW")
    if reasons:
        analysis.risk_blockers = reasons
        analysis.suggested_shares = None
        if analysis.signal in {"BUY", "STRONG_BUY"}:
            analysis.signal = "WAIT"
            analysis.decision = "PORTFOLIO_POLICY_BLOCK"
            analysis.explanation_ar = (
                "قواعد المحفظة بتمنع اقتراح الدخول. راجع أسباب المنع في تقييم المخاطر."
            )
        if add_on:
            if analysis.position.action == "ADD_TO_POSITION":
                analysis.position.action = "WAIT"
            analysis.position.scenario_actions.remove("ADD_TO_POSITION")
            analysis.position.scenarios_ar = [
                line
                for line in analysis.position.scenarios_ar
                if not line.startswith("راجع زيادة المركز")
            ]
            analysis.position.add_on_decision = "USE_PORTFOLIO_REVIEW"
    return analysis


def legacy_entry_blocks(db, security):
    from app.services.sharia_filter import status_for

    policy = load_policy(db)
    sharia_status = status_for(db, security)["status"] if policy.islamic_mode else None
    return entry_blocks(policy, sharia_status, advanced_supported=False)
