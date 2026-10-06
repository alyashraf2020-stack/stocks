from typing import Any, Dict, List, Optional

from app.core.config import settings


class BreakoutEntryAdvisor:
    """Build an alternative breakout entry scenario from validated EOD bars.

    This advisor never mutates OHLCV and never uses the manual live price to
    calculate technical levels. The live price is only compared against levels
    derived from the latest completed EOD dataset.
    """

    @classmethod
    def evaluate(
        cls,
        current_price: float,
        analytical_bars: List[Dict[str, Any]],
        sessions_behind: Optional[int],
        owns_stock: bool = False,
        market_depth: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if sessions_behind is not None and sessions_behind > 0:
            return cls._unavailable(
                "DATA_NOT_CURRENT",
                "بيانات آخر جلسة غير محدثة، لذلك لا يمكن تقييم دخول اختراق حاليًا.",
            )

        if not analytical_bars or len(analytical_bars) < settings.MIN_REQUIRED_BARS:
            return cls._unavailable(
                "INSUFFICIENT_DATA",
                "البيانات التاريخية غير كافية لحساب سيناريو اختراق موثوق.",
            )

        last = analytical_bars[-1]
        close = float(last["close"])
        atr = last.get("atr_14")
        atr = float(atr) if atr is not None and float(atr) > 0 else close * 0.025

        # Recent resistance is derived strictly from completed EOD bars.
        lookback = analytical_bars[-10:]
        resistance = max(float(b["high"]) for b in lookback)

        # Small volatility buffer avoids treating a one-tick touch as a breakout.
        trigger = round(resistance + (0.15 * atr), 2)
        entry_min = trigger
        entry_max = round(trigger + (0.50 * atr), 2)
        stop_loss = round(max(resistance - (0.75 * atr), 0.01), 2)

        risk_unit = round(entry_min - stop_loss, 2)
        if risk_unit <= 0:
            return cls._unavailable(
                "NO_VALID_BREAKOUT_SETUP",
                "تعذر تكوين هندسة مخاطرة صالحة لسيناريو الاختراق الحالي.",
            )

        target_1 = round(entry_min + (settings.TARGET_1_R_MULTIPLE * risk_unit), 2)
        target_2 = round(entry_min + (settings.TARGET_2_R_MULTIPLE * risk_unit), 2)
        target_3 = round(entry_min + (settings.TARGET_3_R_MULTIPLE * risk_unit), 2)

        sma20 = last.get("sma_20")
        sma50 = last.get("sma_50")
        trend_ok = True
        if sma20 is not None:
            trend_ok = trend_ok and close >= float(sma20)
        if sma50 is not None:
            trend_ok = trend_ok and close >= float(sma50)

        depth_pressure = (market_depth or {}).get("pressure", "UNKNOWN")
        depth_status = (market_depth or {}).get("status", "UNAVAILABLE")

        if current_price < trigger:
            decision = "WAIT_FOR_BREAKOUT"
            decision_ar = "انتظر الاختراق"
            reason_ar = (
                f"إذا لم يحدث تراجع مناسب، راقب اختراق {trigger:.2f} ج.م. "
                f"منطقة دخول الاختراق هي {entry_min:.2f} – {entry_max:.2f} ج.م فقط بعد تحقق الاختراق؛ "
                "لا تعتبر مجرد الاقتراب من المقاومة إشارة شراء."
            )
            actionable = False
        elif current_price <= entry_max:
            if not trend_ok:
                decision = "WAIT_BREAKOUT_CONFIRMATION"
                decision_ar = "الاختراق يحتاج تأكيد"
                reason_ar = (
                    f"السعر تجاوز مستوى الاختراق {trigger:.2f} ج.م لكنه يحتاج تأكيد اتجاه قبل الدخول. "
                    f"لا تطارد السعر فوق {entry_max:.2f} ج.م."
                )
                actionable = False
            elif depth_status == "MANUAL_INPUT" and depth_pressure == "SELL_DOMINANT":
                decision = "WAIT_BREAKOUT_CONFIRMATION"
                decision_ar = "انتظر تأكيد الاختراق"
                reason_ar = (
                    f"السعر داخل نطاق دخول الاختراق {entry_min:.2f} – {entry_max:.2f} ج.م، "
                    "لكن عمق السوق الحالي يميل للبيع؛ انتظر تحسن التوازن قبل التنفيذ."
                )
                actionable = False
            else:
                decision = "ADD_ON_BREAKOUT" if owns_stock else "ENTER_BREAKOUT"
                decision_ar = "تعزيز على الاختراق" if owns_stock else "دخول اختراق"
                confirmation = (
                    " ويفضل دعم من عمق السوق/الحجم"
                    if depth_status != "MANUAL_INPUT"
                    else ""
                )
                reason_ar = (
                    f"السعر دخل نطاق الاختراق المحدد {entry_min:.2f} – {entry_max:.2f} ج.م بعد تجاوز المقاومة الحديثة."
                    f" وقف السيناريو {stop_loss:.2f} ج.م{confirmation}."
                )
                actionable = True
        else:
            decision = "DO_NOT_CHASE_BREAKOUT"
            decision_ar = "لا تطارد الاختراق"
            reason_ar = (
                f"السعر تجاوز الحد الأعلى الآمن لدخول الاختراق {entry_max:.2f} ج.م. "
                "انتظر إعادة اختبار المقاومة المكسورة أو تكوين نطاق جديد بدل الشراء المتأخر."
            )
            actionable = False

        return {
            "status": "VALID",
            "decision": decision,
            "decision_ar": decision_ar,
            "reason_ar": reason_ar,
            "actionable": actionable,
            "resistance_level": round(resistance, 2),
            "trigger_price": trigger,
            "entry_zone_min": entry_min,
            "entry_zone_max": entry_max,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "target_3": target_3,
            "confirmation_ar": (
                "الاختراق محسوب من بيانات EOD المكتملة. يفضل وجود ثبات أعلى مستوى الاختراق وعدم وجود ضغط بيع واضح في عمق السوق."
            ),
            "uses_manual_price_for_levels": False,
        }

    @staticmethod
    def _unavailable(code: str, reason_ar: str) -> Dict[str, Any]:
        return {
            "status": code,
            "decision": code,
            "decision_ar": "سيناريو الاختراق غير متاح",
            "reason_ar": reason_ar,
            "actionable": False,
            "resistance_level": None,
            "trigger_price": None,
            "entry_zone_min": None,
            "entry_zone_max": None,
            "stop_loss": None,
            "target_1": None,
            "target_2": None,
            "target_3": None,
            "confirmation_ar": None,
            "uses_manual_price_for_levels": False,
        }
