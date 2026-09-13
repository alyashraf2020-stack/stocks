from typing import Dict, Any, Optional
from app.services.trade_plan import TradePlanEngine
from app.services.risk_manager import RiskManager

class LiveDecisionEngine:
    """
    Evaluates manual live price against validated technical setups.
    Enforces ZERO-SESSION-LAG HARD GATE:
    If sessions_behind > 0:
      decision = "DATA_NOT_CURRENT"
      actionable_new_trade = False
      NEVER returns ENTER_NOW / BUY.
    """

    @classmethod
    def evaluate(
        cls,
        ticker: str,
        current_price: float,
        capital: float,
        owns_stock: bool = False,
        buy_price: Optional[float] = None,
        shares_owned: Optional[int] = None,
        analytical_bars: Optional[list] = None,
        sessions_behind: Optional[int] = None,
        expected_latest_session: Optional[str] = None,
        latest_available_session: Optional[str] = None,
        actual_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        if current_price <= 0:
            return {
                "decision": "INVALID_PRICE",
                "decision_ar": "السعر غير صالح",
                "reason_ar": "السعر الحالي المدخل يجب أن يكون أكبر من الصفر",
                "status": "ERROR"
            }
        if capital <= 0:
            return {
                "decision": "INVALID_CAPITAL",
                "decision_ar": "رأس المال غير صالح",
                "reason_ar": "رأس المال المدخل يجب أن يكون أكبر من الصفر",
                "status": "ERROR"
            }

        latest_close = analytical_bars[-1]["close"] if (analytical_bars and len(analytical_bars) > 0) else None
        freshness_ar = "محدث" if (sessions_behind == 0) else "غير محدث"

        # 1. HARD GATE: ZERO-SESSION-LAG POLICY
        # If latest completed session is missing (sessions_behind > 0), halt immediately
        bars_count = len(analytical_bars) if analytical_bars else 0
        if sessions_behind is not None and sessions_behind > 0:
            return {
                "ticker": ticker,
                "current_price": current_price,
                "decision": "DATA_NOT_CURRENT",
                "decision_ar": "البيانات تحتاج تحديث",
                "badge_color": "yellow",
                "actionable_new_trade": False,
                "current_analysis_eligible": False,
                "reason_ar": (
                    f"⚠️ بيانات آخر جلسة غير متاحة (متأخرة بـ {sessions_behind} جلسة EGX). "
                    "لا يمكن إصدار توصية دخول حالية حتى وصول بيانات آخر جلسة مكتملة."
                ),
                "expected_latest_session": expected_latest_session,
                "latest_available_session": latest_available_session,
                "latest_close": latest_close,
                "sessions_behind": sessions_behind,
                "freshness_ar": freshness_ar,
                "actual_provider": actual_provider,
                "analytical_bars_count": bars_count,
                "status": "DATA_NOT_CURRENT",
                "trade_plan": None,
                "position_sizing": None
            }

        # 2. Gate: Minimum verified analytical history required
        plan_result = TradePlanEngine.calculate_trade_plan(analytical_bars or [], sessions_behind)
        if plan_result["status"] == "INVALID_INSUFFICIENT_DATA":
            return {
                "ticker": ticker,
                "current_price": current_price,
                "decision": "INSUFFICIENT_DATA",
                "decision_ar": "البيانات غير كافية",
                "badge_color": "yellow",
                "actionable_new_trade": False,
                "current_analysis_eligible": False,
                "reason_ar": plan_result["reason_ar"],
                "expected_latest_session": expected_latest_session,
                "latest_available_session": latest_available_session,
                "sessions_behind": sessions_behind,
                "actual_provider": actual_provider,
                "analytical_bars_count": bars_count,
                "status": "INSUFFICIENT_DATA",
                "trade_plan": None,
                "position_sizing": None
            }
        elif plan_result["status"] == "DATA_NOT_CURRENT":
            return {
                "ticker": ticker,
                "current_price": current_price,
                "decision": "DATA_NOT_CURRENT",
                "decision_ar": "البيانات تحتاج تحديث",
                "badge_color": "yellow",
                "actionable_new_trade": False,
                "current_analysis_eligible": False,
                "reason_ar": plan_result["reason_ar"],
                "expected_latest_session": expected_latest_session,
                "latest_available_session": latest_available_session,
                "sessions_behind": sessions_behind,
                "actual_provider": actual_provider,
                "analytical_bars_count": bars_count,
                "status": "DATA_NOT_CURRENT",
                "trade_plan": None,
                "position_sizing": None
            }

        trade_plan = plan_result["trade_plan"]
        previous_plan = plan_result.get("previous_plan")

        # 3. Handle NO_VALID_SETUP case
        if trade_plan.get("plan_status") == "NO_VALID_SETUP":
            if not owns_stock:
                decision = "NO_VALID_SETUP"
                decision_ar = "لا توجد فرصة دخول صالحة حاليًا"
                badge_color = "amber"
                actionable_new_trade = False
                reason_ar = (
                    "لا توجد فرصة دخول صالحة حاليًا بعد اكتمال أهداف الخطة السابقة. "
                    "لا تطارد السعر؛ انتظر تكوين إعداد فني جديد من البيانات القادمة."
                )
            else:
                decision = "TAKE_PROFIT"
                decision_ar = "جني أرباح"
                badge_color = "green"
                actionable_new_trade = False
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) تجاوز جميع أهداف الخطة السابقة واكتملت أهداف الحركة. "
                    "ينصح بجني الأرباح وحجز العائد لحماية المكاسب."
                )

            return {
                "ticker": ticker,
                "current_price": current_price,
                "decision": decision,
                "decision_ar": decision_ar,
                "badge_color": badge_color,
                "actionable_new_trade": actionable_new_trade,
                "current_analysis_eligible": True,
                "plan_status": "NO_VALID_SETUP",
                "new_entry_allowed": False,
                "reason_ar": reason_ar,
                "owns_stock": owns_stock,
                "buy_price": buy_price if owns_stock else None,
                "shares_owned": shares_owned if owns_stock else None,
                "expected_latest_session": expected_latest_session,
                "latest_available_session": latest_available_session,
                "latest_close": latest_close,
                "sessions_behind": 0,
                "freshness_ar": freshness_ar,
                "actual_provider": actual_provider,
                "analytical_bars_count": len(analytical_bars) if analytical_bars else 0,
                "status": "VALID",
                "trade_plan": trade_plan,
                "previous_plan": previous_plan,
                "position_sizing": None
            }

        entry_min = trade_plan["entry_zone_min"]
        entry_max = trade_plan["entry_zone_max"]
        stop_loss = trade_plan["stop_loss"]
        t1 = trade_plan["target_1"]
        t2 = trade_plan["target_2"]
        t3 = trade_plan["target_3"]

        position_sizing = RiskManager.calculate_position_sizing(
            capital=capital,
            planning_entry=entry_max,
            stop_loss=stop_loss
        )

        # 3. Lifecycle Status Evaluation based on manual current_price
        if current_price >= t3:
            plan_status = "TARGETS_COMPLETED"
            new_entry_allowed = False
        elif current_price <= stop_loss:
            plan_status = "INVALIDATED"
            new_entry_allowed = False
        elif current_price >= t1:
            plan_status = "IN_PROGRESS"
            new_entry_allowed = False
        elif entry_min <= current_price <= entry_max:
            plan_status = "ACTIVE"
            new_entry_allowed = True
        elif current_price < entry_min:
            plan_status = "NOT_TRIGGERED"
            new_entry_allowed = False
        else:
            plan_status = "IN_PROGRESS"
            new_entry_allowed = False

        # 4. Decision Evaluation Logic (Only reached when sessions_behind == 0)
        if not owns_stock:
            if current_price >= t3:
                decision = "DO_NOT_CHASE"
                decision_ar = "لا تدخل الآن"
                badge_color = "amber"
                actionable_new_trade = False
                reason_ar = (
                    "السعر تجاوز جميع أهداف الخطة السابقة. لا تطارد السعر؛ "
                    "انتظر تكوين فرصة دخول جديدة بعد تحديث التحليل."
                )
            elif current_price <= stop_loss:
                decision = "DO_NOT_ENTER"
                decision_ar = "لا تدخل"
                badge_color = "red"
                actionable_new_trade = False
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) كسر مستوى وقف الخسارة ({stop_loss:.2f} ج.م). "
                    "السيناريو الفني أصبح غير صالح ومخاطر الهبوط مرتفعة."
                )
            elif entry_min <= current_price <= entry_max:
                decision = "ENTER_NOW"
                decision_ar = "دخول الآن"
                badge_color = "green"
                actionable_new_trade = True
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) متواجد داخل منطقة الدخول الآمنة المحددة "
                    f"({entry_min:.2f} – {entry_max:.2f} ج.م)، ومستوى وقف الخسارة محدد ومحمي عند {stop_loss:.2f} ج.م، "
                    f"مع عائد مستهدف 1:{trade_plan['target_1']:.2f} ج.م كهدف أول."
                )
            elif current_price > entry_max:
                decision = "WAIT"
                decision_ar = "انتظار"
                badge_color = "amber"
                actionable_new_trade = False
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) أعلى من الحد الأقصى لمنطقة الدخول ({entry_max:.2f} ج.م). "
                    "لا تطارد السعر؛ انتظر جني أرباح مؤقت أو إعادة اختبار منطقة الدخول لتجنب الشراء في قمة فرعية."
                )
            else:
                # stop_loss < current_price < entry_min
                decision = "NEAR_ENTRY"
                decision_ar = "قريب من منطقة الدخول"
                badge_color = "blue"
                actionable_new_trade = False
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) أدنى قليلاً من بداية منطقة الدخول ({entry_min:.2f} ج.م) "
                    f"لكنه أعلى من وقف الخسارة ({stop_loss:.2f} ج.م). انتظر إشارة ارتداد وتأكيد صعود داخل منطقة الدخول."
                )
        else:
            actionable_new_trade = False
            if current_price <= stop_loss:
                decision = "EXIT_STOP_LOSS"
                decision_ar = "خروج"
                badge_color = "red"
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) كسر مستوى وقف الخسارة ({stop_loss:.2f} ج.م). "
                    "يجب الخروج فوراً للحد من تفاقم الخسائر وحماية رأس المال."
                )
            elif current_price >= t3:
                decision = "TAKE_PROFIT"
                decision_ar = "جني أرباح"
                badge_color = "green"
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) تجاوز الهدف الثالث ({t3:.2f} ج.م) واكتملت أهداف الخطة السابقة. "
                    "ينصح بتصفية كامل المركز أو تفعيل وقف ربح متقدم لحجز أقصى عائد."
                )
            elif current_price >= t2:
                decision = "RAISE_STOP_LOSS"
                decision_ar = "رفع وقف الخسارة"
                badge_color = "purple"
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) تجاوز الهدف الثاني ({t2:.2f} ج.م). "
                    f"ينصح بتأمين الصفقة برفع وقف الخسارة إلى مستوى الهدف الأول ({t1:.2f} ج.م)."
                )
            elif current_price >= t1:
                decision = "TAKE_PARTIAL_PROFIT"
                decision_ar = "جني جزء من الأرباح"
                badge_color = "teal"
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) بلغ الهدف الأول ({t1:.2f} ج.م). "
                    "ينصح بجني جزء من الأرباح (نصف الكمية) ونقل أمر الوقف إلى سعر الشراء لتأمين الصفقة."
                )
            else:
                decision = "HOLD"
                decision_ar = "احتفاظ"
                badge_color = "emerald"
                reason_ar = (
                    f"السعر اللحظي ({current_price:.2f} ج.م) يسير بشكل طبيعي أعلى من وقف الخسارة ({stop_loss:.2f} ج.م) "
                    f"وفي طريقه نحو الهدف الأول ({t1:.2f} ج.م). استمر في الاحتفاظ بالمركز."
                )

        trade_plan_output = dict(trade_plan)
        trade_plan_output["plan_status"] = plan_status
        trade_plan_output["new_entry_allowed"] = new_entry_allowed

        return {
            "ticker": ticker,
            "current_price": current_price,
            "decision": decision,
            "decision_ar": decision_ar,
            "badge_color": badge_color,
            "actionable_new_trade": actionable_new_trade,
            "current_analysis_eligible": True,
            "plan_status": plan_status,
            "new_entry_allowed": new_entry_allowed,
            "reason_ar": reason_ar,
            "owns_stock": owns_stock,
            "buy_price": buy_price if owns_stock else None,
            "shares_owned": shares_owned if owns_stock else None,
            "expected_latest_session": expected_latest_session,
            "latest_available_session": latest_available_session,
            "latest_close": latest_close,
            "sessions_behind": 0,
            "freshness_ar": freshness_ar,
            "actual_provider": actual_provider,
            "analytical_bars_count": len(analytical_bars) if analytical_bars else 0,
            "status": "VALID",
            "trade_plan": trade_plan_output,
            "previous_plan": previous_plan,
            "position_sizing": None if owns_stock else position_sizing
        }