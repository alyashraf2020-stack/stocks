import math
from typing import List, Dict, Any, Optional
from app.core.config import settings

class TradePlanEngine:
    """
    Centralized deterministic TradePlanEngine for long-only EGX trading setups.
    Enforces ZERO-SESSION-LAG POLICY:
    - sessions_behind == 0 is MANDATORY for actionable new trade plans.
    - If sessions_behind > 0: status = DATA_NOT_CURRENT, actionable_new_trade = False.
    """

    @classmethod
    def calculate_trade_plan(
        cls,
        analytical_bars: List[Dict[str, Any]],
        sessions_behind: Optional[int] = None
    ) -> Dict[str, Any]:
        # 1. Gate: Minimum verified analytical history required (>= 50 bars)
        if not analytical_bars or len(analytical_bars) < settings.MIN_REQUIRED_BARS:
            return {
                "status": "INVALID_INSUFFICIENT_DATA",
                "actionable_new_trade": False,
                "current_analysis_eligible": False,
                "reason_ar": "البيانات التاريخية غير كافية لحساب نموذج تداول موثوق (يلزم 50 جلسة تداول على الأقل)",
                "trade_plan": None
            }

        # 2. Gate: ZERO-SESSION-LAG POLICY (Strict: sessions_behind must be exactly 0)
        if sessions_behind is not None and sessions_behind > 0:
            return {
                "status": "DATA_NOT_CURRENT",
                "actionable_new_trade": False,
                "current_analysis_eligible": False,
                "reason_ar": f"بيانات آخر جلسة غير متاحة — متأخرة بـ {sessions_behind} جلسة EGX. لا يمكن إصدار توصية دخول حالية حتى وصول بيانات آخر جلسة مكتملة.",
                "trade_plan": None
            }

        last_bar = analytical_bars[-1]
        current_close = float(last_bar["close"])
        
        # Lookback window for technical support & resistance (past 20 valid sessions)
        lookback_bars = analytical_bars[-20:]
        recent_lows = [float(b["low"]) for b in lookback_bars]
        recent_highs = [float(b["high"]) for b in lookback_bars]

        support_level = round(min(recent_lows), 2)
        resistance_level = round(max(recent_highs), 2)

        atr = last_bar.get("atr_14")
        if atr is None or atr <= 0:
            atr = current_close * 0.025  # Conservative 2.5% proxy if ATR not computed

        # 3. Deterministic Stop Loss calculation
        candidate_stop = support_level - (0.5 * atr)
        stop_loss = round(max(candidate_stop, 0.01), 2)
        stop_basis = f"وقف الخسارة محدد أسفل مستوى الدعم الفني ({support_level:.2f} ج.م) مع هامش تقلب فني 0.5 ATR ({0.5 * atr:.2f} ج.م)"

        # 4. Deterministic Entry Zone calculation
        entry_zone_min = round(max(support_level, stop_loss + (0.5 * atr)), 2)
        entry_buffer = 0.8 * atr
        entry_zone_max = round(min(resistance_level, entry_zone_min + entry_buffer), 2)

        # Enforce strict geometry: stop_loss < entry_zone_min <= entry_zone_max
        if entry_zone_min <= stop_loss:
            entry_zone_min = round(stop_loss + (0.5 * atr), 2)
        if entry_zone_max < entry_zone_min:
            entry_zone_max = entry_zone_min

        entry_basis = f"نطاق التجميع الفني بين مستوى الدعم ({entry_zone_min:.2f} ج.م) وحد الدخول الآمن ({entry_zone_max:.2f} ج.م)"

        # 5. Planning Entry & Transparent R-Multiples
        planning_entry = entry_zone_max
        r_unit = round(planning_entry - stop_loss, 2)
        if r_unit <= 0:
            r_unit = round(planning_entry * 0.03, 2)
            stop_loss = round(planning_entry - r_unit, 2)

        target_1 = round(planning_entry + (settings.TARGET_1_R_MULTIPLE * r_unit), 2)
        target_2 = round(planning_entry + (settings.TARGET_2_R_MULTIPLE * r_unit), 2)
        target_3 = round(planning_entry + (settings.TARGET_3_R_MULTIPLE * r_unit), 2)

        assert stop_loss < entry_zone_min <= entry_zone_max
        assert planning_entry < target_1 < target_2 < target_3

        # 6. Multi-Factor Informational Score (0-100)
        factor_breakdown, score, strength = cls.calculate_factor_score(analytical_bars)

        # 7. Trade-Plan Lifecycle Status (relative to latest completed session)
        if current_close >= target_3:
            plan_status = "TARGETS_COMPLETED"
            new_entry_allowed = False
        elif current_close <= stop_loss:
            plan_status = "INVALIDATED"
            new_entry_allowed = False
        elif current_close >= target_1:
            plan_status = "IN_PROGRESS"
            new_entry_allowed = False
        elif entry_zone_min <= current_close <= entry_zone_max:
            plan_status = "ACTIVE"
            new_entry_allowed = True
        elif current_close < entry_zone_min:
            plan_status = "NOT_TRIGGERED"
            new_entry_allowed = False
        else:
            plan_status = "IN_PROGRESS"
            new_entry_allowed = False

        trade_plan = {
            "entry_zone_min": entry_zone_min,
            "entry_zone_max": entry_zone_max,
            "planning_entry": planning_entry,
            "stop_loss": stop_loss,
            "r_unit": r_unit,
            "target_1": target_1,
            "target_2": target_2,
            "target_3": target_3,
            "support_level": support_level,
            "resistance_level": resistance_level,
            "entry_basis": entry_basis,
            "stop_basis": stop_basis,
            "factor_score": score,
            "analysis_strength": strength,
            "factor_breakdown": factor_breakdown,
            "plan_status": plan_status,
            "new_entry_allowed": new_entry_allowed,
            "trigger_condition": "دخول عند ملامسة منطقة الدخول مع استقرار السعر"
        }

        previous_plan = None
        if current_close >= target_3:
            previous_plan = dict(trade_plan)
            previous_plan["plan_status"] = "TARGETS_COMPLETED"
            previous_plan["new_entry_allowed"] = False

            # Check if a new valid setup exists at current levels or if overbought
            rsi = last_bar.get("rsi_14")
            if rsi is not None and rsi > 75.0:
                trade_plan = {
                    "entry_zone_min": None,
                    "entry_zone_max": None,
                    "planning_entry": None,
                    "stop_loss": None,
                    "r_unit": None,
                    "target_1": None,
                    "target_2": None,
                    "target_3": None,
                    "support_level": support_level,
                    "resistance_level": resistance_level,
                    "entry_basis": "لا توجد فرصة دخول صالحة حاليًا بعد اكتمال أهداف الخطة السابقة",
                    "stop_basis": "انتظر تكوين قاع فني جديد",
                    "factor_score": score,
                    "analysis_strength": strength,
                    "factor_breakdown": factor_breakdown,
                    "plan_status": "NO_VALID_SETUP",
                    "new_entry_allowed": False,
                    "trigger_condition": "انتظر تكوين إعداد فني جديد من البيانات القادمة"
                }

        return {
            "status": "VALID",
            "actionable_new_trade": trade_plan["new_entry_allowed"],
            "current_analysis_eligible": True,
            "reason_ar": "تم حساب النموذج الفني بنجاح بناءً على بيانات تاريخية موثقة حتى آخر جلسة مكتملة",
            "trade_plan": trade_plan,
            "previous_plan": previous_plan
        }

    @classmethod
    def calculate_factor_score(cls, bars: List[Dict[str, Any]]) -> (Dict[str, int], int, str):
        last = bars[-1]
        close = float(last["close"])
        sma20 = last.get("sma_20")
        sma50 = last.get("sma_50")
        rsi = last.get("rsi_14")
        macd_hist = last.get("macd_hist")
        atr = last.get("atr_14")

        trend_pts = 0
        if sma20 is not None and close > sma20:
            trend_pts += 10
        if sma50 is not None and close > sma50:
            trend_pts += 10
        if sma20 is not None and sma50 is not None and sma20 > sma50:
            trend_pts += 5

        momentum_pts = 0
        if rsi is not None:
            if 45.0 <= rsi <= 65.0:
                momentum_pts += 15
            elif 40.0 <= rsi <= 70.0:
                momentum_pts += 10
        if macd_hist is not None and macd_hist > 0:
            momentum_pts += 10

        structure_pts = 0
        lookback_20 = bars[-20:]
        min_low = min(float(b["low"]) for b in lookback_20)
        if close > min_low:
            structure_pts += 15
        half_1 = lookback_20[:10]
        half_2 = lookback_20[10:]
        if min(float(b["low"]) for b in half_2) >= min(float(b["low"]) for b in half_1):
            structure_pts += 10

        liq_pts = 0
        vol_recent = float(last.get("volume", 0.0))
        vol_avg_20 = sum(float(b.get("volume", 0.0)) for b in lookback_20) / 20.0
        if vol_recent >= vol_avg_20:
            liq_pts += 15
        elif vol_recent > 0:
            liq_pts += 8
        
        if atr is not None and close > 0:
            rel_atr = (atr / close) * 100.0
            if 1.0 <= rel_atr <= 6.0:
                liq_pts += 10

        total_score = min(100, trend_pts + momentum_pts + structure_pts + liq_pts)

        if total_score >= 70:
            strength_ar = "قوي"
        elif total_score >= 50:
            strength_ar = "معتدل"
        else:
            strength_ar = "ضعيف"

        breakdown = {
            "trend": trend_pts,
            "momentum": momentum_pts,
            "price_structure": structure_pts,
            "liquidity_volatility": liq_pts
        }

        return breakdown, total_score, strength_ar