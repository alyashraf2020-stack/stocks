"""Conditional EOD plans for every listed security; never a fabricated live quote."""
import datetime
import logging
import math
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.security import EGXSecurity
from app.services.breakout_entry import BreakoutEntryAdvisor
from app.services.data_provider.manager import default_provider_manager
from app.services.egx_calendar import get_expected_latest_completed_session, calculate_sessions_behind
from app.services.indicators import TechnicalIndicatorEngine
from app.services.trade_plan import TradePlanEngine

logger = logging.getLogger(__name__)


def valid_levels(plan):
    if not plan:
        return False
    try:
        values = [float(plan[key]) for key in (
            "stop_loss", "entry_zone_min", "entry_zone_max", "target_1", "target_2", "target_3"
        )]
        stop, lower, upper, t1, t2, t3 = values
        return all(math.isfinite(v) and v > 0 for v in values) and stop < lower <= upper < t1 < t2 < t3
    except (KeyError, ValueError, TypeError):
        return False


class StockPlansService:
    @staticmethod
    def build(db: Session, security: EGXSecurity, refresh: bool = False):
        expected = get_expected_latest_completed_session()
        result = {
            "ticker": security.ticker, "arabic_name": security.arabic_name,
            "english_name": security.english_name, "sector": security.sector,
            "listing_status": security.listing_status,
            "status": "DATA_UNAVAILABLE", "status_ar": "البيانات غير متاحة",
            "reason_ar": "لم تتوفر جلسات موثقة لهذا السهم. اضغط تحديث لجلب البيانات من المصادر.",
            "expected_latest_session": expected.isoformat(),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "price_basis": "LAST_COMPLETED_SESSION_CLOSE",
            "trade_plan": None, "breakout_entry": None,
        }
        if security.listing_status != "ACTIVE":
            return {**result, "status": "INACTIVE_SECURITY", "status_ar": "السهم غير نشط",
                    "reason_ar": "حالة القيد الحالية لا تسمح بإصدار خطة دخول جديدة."}
        try:
            data = default_provider_manager.get_analytical_bars(
                security.ticker, db=db, limit=250, allow_network=refresh,
            )
            # Require actual completed dates and finite prices; future/intraday bars
            # must not make the all-stocks view appear current.
            bars = []
            for bar in data.get("bars", []):
                try:
                    date = datetime.date.fromisoformat(bar["session_date"])
                    values = [float(bar[key]) for key in ("high", "low", "close", "volume")]
                    if date <= expected and all(math.isfinite(value) for value in values):
                        bars.append(bar)
                except (KeyError, ValueError, TypeError):
                    continue
            bars.sort(key=lambda bar: bar["session_date"])
            latest = bars[-1] if bars else None
            latest_date = datetime.date.fromisoformat(latest["session_date"]) if latest else None
            behind = calculate_sessions_behind(latest_date) if latest_date else None
            result.update({
                "latest_available_session": latest["session_date"] if latest else None,
                "latest_close": latest["close"] if latest else None,
                "sessions_behind": behind,
                "actual_provider": latest.get("actual_provider") if latest else data.get("actual_provider"),
                "analytical_bars_count": len(bars),
            })
            if not bars:
                return result
            if latest_date != expected or behind != 0:
                return {**result, "status": "DATA_NOT_CURRENT", "status_ar": "تحتاج تحديث",
                        "reason_ar": f"آخر جلسة موثقة {latest_date}. يلزم وصول جلسة {expected} قبل إظهار أسعار الدخول والوقف."}
            if len(bars) < settings.MIN_REQUIRED_BARS:
                return {**result, "status": "INSUFFICIENT_DATA", "status_ar": "التاريخ غير كافٍ",
                        "reason_ar": f"متاح {len(bars)} جلسة صالحة؛ يلزم {settings.MIN_REQUIRED_BARS} جلسة لحساب الخطة."}

            enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
            pullback = TradePlanEngine.calculate_trade_plan(enriched, sessions_behind=0)
            plan = pullback.get("trade_plan")
            if not valid_levels(plan):
                plan = None
            breakout = BreakoutEntryAdvisor.evaluate(
                current_price=float(latest["close"]), analytical_bars=enriched, sessions_behind=0,
            )
            if not valid_levels(breakout):
                breakout = None
            # The dashboard is a watch plan based on EOD, never "buy now".
            if breakout:
                breakout = {**breakout, "actionable": False}
            lifecycle_labels = {
                "ACTIVE": "داخل نطاق الدخول عند الإغلاق",
                "NOT_TRIGGERED": "انتظار تأكيد الدخول",
                "IN_PROGRESS": "انتظار عودة السعر للنطاق",
                "INVALIDATED": "الخطة ملغاة بكسر الوقف",
                "TARGETS_COMPLETED": "الخطة حققت أهدافها",
            }
            return {
                **result, "status": "PLAN_AVAILABLE" if plan or breakout else "NO_VALID_SETUP",
                "status_ar": "خطة متاحة" if plan or breakout else "لا توجد خطة صالحة",
                "reason_ar": "خطة فنية شرطية من آخر إغلاق مكتمل. راجع سعر الوسيط وتحقق من شرط الدخول قبل التنفيذ.",
                "pullback_status_ar": lifecycle_labels.get(plan.get("plan_status"), "خطة مشروطة") if plan else None,
                "trade_plan": plan, "breakout_entry": breakout,
            }
        except Exception:
            logger.exception("Could not build EOD plan for %s", security.ticker)
            return {**result, "status": "ERROR", "status_ar": "تعذر حساب الخطة",
                    "reason_ar": "حدث خطأ عند قراءة أو حساب بيانات هذا السهم. أعد المحاولة من زر تحديث."}

    @classmethod
    def overview(cls, db: Session):
        securities = db.query(EGXSecurity).order_by(EGXSecurity.ticker).all()
        return {
            "total": len(securities),
            "expected_latest_session": get_expected_latest_completed_session().isoformat(),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "items": [cls.build(db, security) for security in securities],
        }
