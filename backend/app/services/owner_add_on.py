import math
from typing import Any, Dict, Optional
from app.core.config import settings


class OwnerAddOnAdvisor:
    """Evaluate whether an existing holder should add more shares.

    This is deliberately separate from position-management decisions. It never
    turns news or market-depth context into a buy signal by itself.
    """

    @classmethod
    def evaluate(
        cls,
        current_price: float,
        capital: float,
        shares_owned: Optional[int],
        trade_plan: Optional[Dict[str, Any]],
        sessions_behind: Optional[int],
    ) -> Dict[str, Any]:
        if sessions_behind is not None and sessions_behind > 0:
            return cls._result(
                "DATA_NOT_CURRENT",
                "لا تعزز الآن",
                "بيانات آخر جلسة غير محدثة، لذلك لا يمكن تقييم التعزيز بأمان.",
            )

        if not trade_plan or trade_plan.get("plan_status") == "NO_VALID_SETUP":
            return cls._result(
                "NO_VALID_SETUP",
                "لا تعزز الآن",
                "لا توجد خطة دخول حالية صالحة للتعزيز. انتظر تكوين إعداد فني جديد من بيانات جلسة مكتملة.",
            )

        required = ("entry_zone_min", "entry_zone_max", "stop_loss")
        if any(trade_plan.get(k) is None for k in required):
            return cls._result(
                "NO_VALID_SETUP",
                "لا تعزز الآن",
                "الخطة الحالية لا تحتوي على منطقة دخول ووقف خسارة صالحين للتعزيز.",
            )

        entry_min = float(trade_plan["entry_zone_min"])
        entry_max = float(trade_plan["entry_zone_max"])
        stop_loss = float(trade_plan["stop_loss"])
        owned = max(int(shares_owned or 0), 0)

        max_allocation_value = capital * settings.MAX_ALLOCATION_PCT
        current_position_value = current_price * owned
        remaining_allocation = max(max_allocation_value - current_position_value, 0.0)

        max_risk_value = capital * settings.MAX_RISK_PER_TRADE_PCT
        # Conservative mark-to-stop risk for the existing holding.
        existing_risk_to_stop = max(current_price - stop_loss, 0.0) * owned
        remaining_risk = max(max_risk_value - existing_risk_to_stop, 0.0)

        risk_per_added_share = max(entry_max - stop_loss, 0.0)
        shares_by_allocation = math.floor(remaining_allocation / entry_max) if entry_max > 0 else 0
        shares_by_risk = (
            math.floor(remaining_risk / risk_per_added_share)
            if risk_per_added_share > 0
            else 0
        )
        suggested_add_on_shares = max(min(shares_by_allocation, shares_by_risk), 0)

        sizing = {
            "current_position_value_egp": round(current_position_value, 2),
            "max_total_allocation_egp": round(max_allocation_value, 2),
            "remaining_allocation_egp": round(remaining_allocation, 2),
            "existing_risk_to_stop_egp": round(existing_risk_to_stop, 2),
            "remaining_risk_budget_egp": round(remaining_risk, 2),
            "suggested_add_on_shares": suggested_add_on_shares,
            "estimated_add_on_value_egp": round(suggested_add_on_shares * entry_max, 2),
        }

        if suggested_add_on_shares <= 0:
            return cls._result(
                "NO_ADD_CAPACITY",
                "لا تعزز الآن",
                "المركز الحالي استهلك حد التخصيص أو ميزانية المخاطرة المسموح بها للتعزيز.",
                entry_min,
                entry_max,
                sizing,
            )

        if current_price <= stop_loss:
            return cls._result(
                "DO_NOT_ADD",
                "لا تعزز",
                f"السعر الحالي كسر وقف الخسارة {stop_loss:.2f} ج.م؛ التعزيز غير مناسب قبل تكوين خطة جديدة.",
                entry_min,
                entry_max,
                sizing,
            )

        if entry_min <= current_price <= entry_max:
            return cls._result(
                "ADD_NOW",
                "تعزيز الآن",
                f"السعر داخل منطقة التعزيز الفنية الحالية {entry_min:.2f} – {entry_max:.2f} ج.م مع بقاء مساحة ضمن حدود المخاطرة والتخصيص.",
                entry_min,
                entry_max,
                sizing,
            )

        if current_price > entry_max:
            return cls._result(
                "WAIT_TO_ADD",
                "انتظر للتعزيز",
                f"السعر أعلى من منطقة التعزيز {entry_min:.2f} – {entry_max:.2f} ج.م. لا تطارد السعر؛ انتظر إعادة اختبار المنطقة أو خطة جديدة.",
                entry_min,
                entry_max,
                sizing,
            )

        return cls._result(
            "WAIT_CONFIRMATION",
            "انتظر تأكيدًا قبل التعزيز",
            f"السعر أسفل منطقة التعزيز {entry_min:.2f} – {entry_max:.2f} ج.م لكنه أعلى من وقف الخسارة. انتظر ارتدادًا مؤكدًا داخل المنطقة.",
            entry_min,
            entry_max,
            sizing,
        )

    @staticmethod
    def _result(
        code: str,
        label_ar: str,
        reason_ar: str,
        zone_min: Optional[float] = None,
        zone_max: Optional[float] = None,
        sizing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "decision": code,
            "decision_ar": label_ar,
            "reason_ar": reason_ar,
            "entry_zone_min": zone_min,
            "entry_zone_max": zone_max,
            "sizing": sizing,
        }
