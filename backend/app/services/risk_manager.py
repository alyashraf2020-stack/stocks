import math
from typing import Dict, Any
from app.core.config import settings

class RiskManager:
    """
    Strict risk and position sizing engine.
    Rules:
    - Maximum capital risk per trade: 1.5% (fixed)
    - Maximum capital allocation per stock: 20.0% (fixed)
    - Planning entry = entry_zone_max (conservative upper boundary)
    - Neither risk constraint is ever exceeded.
    """

    @classmethod
    def calculate_position_sizing(
        cls,
        capital: float,
        planning_entry: float,
        stop_loss: float
    ) -> Dict[str, Any]:
        if capital <= 0:
            raise ValueError("رأس المال يجب أن يكون أكبر من الصفر")
        if planning_entry <= 0 or stop_loss <= 0:
            raise ValueError("سعر الدخول ووقف الخسارة يجب أن يكونا أكبر من الصفر")
        if stop_loss >= planning_entry:
            raise ValueError("وقف الخسارة يجب أن يكون أقل من سعر الدخول")

        risk_amount_allowed = capital * settings.MAX_RISK_PER_TRADE_PCT
        allocation_amount_allowed = capital * settings.MAX_ALLOCATION_PCT

        risk_per_share = planning_entry - stop_loss
        shares_by_risk = math.floor(risk_amount_allowed / risk_per_share)
        shares_by_allocation = math.floor(allocation_amount_allowed / planning_entry)

        suggested_shares = min(shares_by_risk, shares_by_allocation)
        position_value = round(suggested_shares * planning_entry, 2)
        max_expected_loss = round(suggested_shares * risk_per_share, 2)

        actual_risk_pct = round((max_expected_loss / capital) * 100.0, 2) if capital > 0 else 0.0
        actual_allocation_pct = round((position_value / capital) * 100.0, 2) if capital > 0 else 0.0

        # Enforce guarantees
        assert max_expected_loss <= risk_amount_allowed + 1e-5
        assert position_value <= allocation_amount_allowed + 1e-5

        return {
            "capital": capital,
            "planning_entry": planning_entry,
            "stop_loss": stop_loss,
            "risk_per_share": round(risk_per_share, 2),
            "max_risk_allowed_egp": round(risk_amount_allowed, 2),
            "max_allocation_allowed_egp": round(allocation_amount_allowed, 2),
            "shares_by_risk": shares_by_risk,
            "shares_by_allocation": shares_by_allocation,
            "suggested_shares": suggested_shares,
            "position_value_egp": position_value,
            "max_expected_loss_egp": max_expected_loss,
            "actual_risk_pct": actual_risk_pct,
            "actual_allocation_pct": actual_allocation_pct
        }