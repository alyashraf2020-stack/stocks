"""Project typed market data into conditional analysis and a minimal model context."""

from datetime import datetime, time, timedelta, timezone

from app.core.config import settings
from app.schemas.ai_analysis import Analysis, PlanLevels, PositionReview
from app.schemas.ai_analysis import EvidenceCode as E
from app.schemas.thndr import Quote
from app.services.breakout_entry import BreakoutEntryAdvisor
from app.services.corporate_events import CorporateEventService
from app.services.data_provider.manager import default_provider_manager
from app.services.decision_engine import LiveDecisionEngine
from app.services.egx_calendar import (
    CAIRO_TZ,
    get_expected_latest_completed_session,
    is_egx_trading_day,
)
from app.services.indicators import TechnicalIndicatorEngine
from app.services.owner_add_on import OwnerAddOnAdvisor
from app.services.quote_freshness import validate_quote
from app.services.risk_manager import RiskManager
from app.services.risk_policy import apply_analysis_policy
from app.services.stock_plans import valid_levels
from app.services.technical_rating import TechnicalRatingEngine
from app.services.trade_plan import TradePlanEngine
from app.services.validator import completed_analytical_bars

PHRASES = {
    E.TREND_SUPPORT: "اتجاه السعر في الجلسات المكتملة بيدعم الخطة.",
    E.MOMENTUM_SUPPORT: "مؤشرات الزخم بتميل للصعود.",
    E.VOLUME_SUPPORT: "حجم التداول في آخر جلسة أعلى من متوسطه.",
    E.BREAKOUT: "السعر المرجعي داخل نطاق الاختراق المحسوب. تأكيده محتاج بيانات تداول حديثة.",
    E.ENTRY_ZONE: "السعر المرجعي داخل النطاق المحسوب للدخول.",
    E.TREND_WEAK: "اتجاه السعر في الجلسات المكتملة ضعيف.",
    E.MOMENTUM_WEAK: "مؤشرات الزخم بتميل للهبوط.",
    E.CONFLICT: "الاتجاه والزخم بيدّوا إشارات مختلفة. الانتظار ممكن يكون أنسب لحد ما يتوافقوا.",
    E.THIN_VOLUME: "حجم التداول ضعيف مقارنة بمتوسطه أو المتوسط غير متاح.",
    E.VOLATILITY: "التذبذب مرتفع، والسعر ممكن يتحرك بسرعة ناحية الوقف.",
    E.CHASING: "السعر المرجعي أعلى من النطاق. الشراء عنده يبقى مطاردة للسعر.",
    E.WAIT_ENTRY: "انتظر عودة السعر للنطاق وتأكيد شرط الدخول قبل مراجعة الخطة.",
    E.EXIT_ZONE: "السعر المرجعي وصل لمستوى من مستويات إدارة المركز.",
    E.STALE_DATA: "بيانات الجلسة المطلوبة لسه غير متاحة. انتظر تحديثها قبل تقييم الدخول.",
    E.PRICE_UNVERIFIED: "المرجع السعري محتاج تحقق من السوق قبل أي تصرّف.",
    E.FUNDAMENTALS_MISSING: "البيانات المالية الحديثة الموثقة غير متاحة للتحليل ده.",
    E.EVENT_RISK: "فيه إفصاح شركة مرتبط بالفترة. راجع تأثيره قبل اتخاذ قرار.",
    E.EXPOSURE: "المركز وصل لحد التخصيص للسهم أو تجاوزه.",
    E.NO_SETUP: "الشروط الحالية ما بتقدّمش خطة دخول صالحة.",
}


def plan_levels(plan):
    if not valid_levels(plan):
        return None
    entry = plan["entry_zone_max"]
    stop = plan["stop_loss"]
    targets = tuple(plan[f"target_{n}"] for n in (1, 2, 3))
    return PlanLevels(
        lower=plan["entry_zone_min"],
        upper=entry,
        stop=stop,
        targets=targets,
        reward_to_risk=tuple(
            round((target - entry) / (entry - stop), 2) for target in targets
        ),
        support=plan.get("support_level"),
        resistance=plan.get("resistance_level"),
    )


def session_status(now):
    local = now.astimezone(CAIRO_TZ)
    if is_egx_trading_day(local.date()) and time(10) <= local.time() < time(14, 30):
        return "OPEN"
    return "CLOSED"


def position_inputs(request, brokerage):
    if request.source == "THNDR":
        if brokerage is None:
            return None, None, None
        matches = [
            position
            for position in (brokerage.holdings or [])
            if position.ticker == request.ticker
        ]
        holding = matches[0] if len(matches) == 1 else None
        return holding, brokerage.total_value, brokerage.available_cash
    return request.position, request.portfolio_value, request.cash


def position_review(request, holding, capital, cash, report, live, plan):
    broker = request.source == "THNDR"
    quantity = holding.quantity if broker else holding.shares
    basis = holding.average_price
    price = report.price
    exposure = (
        round(quantity * price * 100 / capital, 2)
        if quantity and price and capital
        else None
    )
    pnl = holding.unrealized_pnl if broker else None
    if quantity is not None and basis and price:
        pnl = round((price - basis) * quantity, 2)
    actions = {
        "HOLD": "HOLD",
        "EXIT_STOP_LOSS": "FULL_EXIT",
        "TAKE_PROFIT": "FULL_EXIT",
        "TAKE_PARTIAL_PROFIT": "TAKE_PARTIAL_PROFIT",
        "RAISE_STOP_LOSS": "MOVE_STOP_LOSS",
    }
    action = actions.get(live, "WAIT")
    scenarios = []
    add_on = None
    scenario_actions = []
    if report.levels:
        scenario_actions.extend(["FULL_EXIT", "TAKE_PARTIAL_PROFIT", "MOVE_STOP_LOSS"])
        scenarios = [
            "راجع الخروج لو السعر المؤكد كسر الوقف.",
            "راجع تخفيف جزء من المركز أو جني جزء من الربح عند الهدف الأول.",
            "راجع رفع الوقف عند الهدف الثاني بعد تأكيد السعر.",
        ]
        if action in {"HOLD", "WAIT"} and not broker and capital and price and quantity:
            add_on = OwnerAddOnAdvisor.evaluate(
                price,
                capital,
                quantity,
                plan,
                0,
                basis,
                cash if cash is not None and cash <= capital else None,
            )
            if (
                add_on["decision"] == "ADD_NOW"
                and report.score is not None
                and report.score > 10
            ):
                action = "ADD_TO_POSITION"
                report.suggested_shares = add_on["sizing"]["suggested_add_on_shares"]
            if (add_on.get("sizing") or {}).get("suggested_add_on_shares", 0) > 0:
                scenario_actions.append("ADD_TO_POSITION")
                scenarios.append(
                    "راجع زيادة المركز فقط مع تأكيد الدخول ووجود سعة في الكاش وحدود المخاطرة والتخصيص."
                )
        if (
            action == "HOLD"
            and report.trend_score is not None
            and report.trend_score < -10
        ):
            scenario_actions.append("PARTIAL_SELL")
            scenarios.append(
                "راجع تخفيف جزء من المركز لو ضعف الاتجاه استمر واتأكد بسعر السوق."
            )
    if broker and report.freshness != "REALTIME_VERIFIED":
        action = "WAIT"
    return PositionReview(
        source=request.source,
        shares=quantity,
        average_price=basis,
        unrealized_pnl=pnl,
        exposure_pct=exposure,
        action=action,
        scenario_actions=scenario_actions,
        scenarios_ar=scenarios,
        add_on_decision=add_on["decision"] if add_on else None,
    )


def build_analysis(
    db, security, request, brokerage=None, *, for_risk_review=False,
    scan_time=None, completed_session=None,
):
    now = scan_time or datetime.now(timezone.utc)
    expected = completed_session or get_expected_latest_completed_session(now)
    market = session_status(now)
    if brokerage and brokerage.market_status == "HALTED":
        market = "HALTED"
    history = default_provider_manager.get_analytical_bars(
        security.ticker, db=db, limit=250, allow_network=False,
        **({"completed_session": completed_session} if completed_session else {}),
    )
    bars = completed_analytical_bars(history.get("bars", []), expected, security.ticker)
    latest = bars[-1] if bars else {}
    reference_session = latest.get("session_date")
    price, provider, stamp = latest.get("close"), latest.get("actual_provider"), None
    freshness = "HISTORICAL" if price is not None else "UNKNOWN"
    holding, capital, cash = position_inputs(request, brokerage)
    identity_valid = bool(security.isin)
    rejected_quote = False
    plan = None
    if request.source == "THNDR" and holding:
        identity_valid = identity_valid and holding.instrument_id == security.isin
        if holding.quote:
            quote = Quote.model_validate(
                holding.quote.model_dump(include=set(Quote.model_fields))
            )
            checked = validate_quote(
                quote, ticker=security.ticker, instrument_id=security.isin, now=now
            )
            if identity_valid and checked.validation_status == "VALID":
                price, provider, stamp, freshness = (
                    checked.price,
                    checked.provider,
                    checked.source_timestamp,
                    checked.freshness,
                )
            else:
                rejected_quote = True
    if request.manual_price is not None:
        price, provider, freshness = request.manual_price, "MANUAL_INPUT", "MANUAL"

    report = Analysis(
        ticker=security.ticker,
        company=security.arabic_name,
        sector=security.sector,
        signal="NO_TRADE",
        decision="NO_VALID_SETUP",
        explanation_ar=PHRASES[E.NO_SETUP],
        price=price,
        provider=provider,
        price_timestamp=stamp,
        reference_session=reference_session,
        freshness=freshness,
        market_status=market,
    )
    report.missing_ar = [
        "قوائم مالية موثقة بتاريخ حديث",
        "بيانات دفتر الأوامر والسيولة اللحظية",
    ]
    if capital is None:
        report.missing_ar.append("إجمالي قيمة المحفظة لحساب حجم المركز")
    if request.source == "THNDR" and not holding:
        report.missing_ar.append("مركز مطابق من ثاندر")
    if request.source == "THNDR" and holding and not holding.quote:
        report.missing_ar.append("سعر حديث للمركز من ثاندر")
    if rejected_quote:
        report.missing_ar.append(
            "سعر ثاندر مرفوض بسبب الهوية أو التوقيت أو بيانات التسعير"
        )
    if not identity_valid:
        report.missing_ar.append("ترقيم دولي مطابق")
    if stamp is None:
        report.missing_ar.append("توقيت سعر لحظي موثّق")
    report.company_events = [
        {key: event[key] for key in ("event_date", "title_ar", "source_url")}
        for event in CorporateEventService.get_relevant_events(
            security.ticker, now.astimezone(CAIRO_TZ).date()
        )
    ]
    rating = (
        TechnicalRatingEngine.calculate(
            bars, current=reference_session == expected.isoformat()
        )
        if bars
        else None
    )
    if rating:
        for name, key in (
            ("technical_rating", "signal"),
            ("score", "score"),
            ("agreement_pct", "agreement_pct"),
            ("trend_score", "trend_score"),
            ("momentum_score", "momentum_score"),
            ("relative_volume", "relative_volume"),
            ("mean_volume", "mean_volume_20"),
            ("volatility_pct", "atr_pct"),
        ):
            setattr(report, name, rating[key])

    if security.listing_status != "ACTIVE" or not identity_valid or market == "HALTED":
        report.decision, report.explanation_ar = (
            "UNVERIFIED_OR_INACTIVE",
            "الهوية أو حالة قيد السهم تمنع تقييم صفقة.",
        )
    elif not bars:
        report.signal = report.decision = "INSUFFICIENT_DATA"
        report.explanation_ar = "مفيش جلسات مكتملة كفاية للتحليل."
    elif reference_session != expected.isoformat():
        report.signal = report.decision = "DATA_NOT_CURRENT"
        report.explanation_ar = PHRASES[E.STALE_DATA]
        if report.freshness == "HISTORICAL":
            report.freshness = "STALE"
    elif len(bars) < settings.MIN_REQUIRED_BARS:
        report.signal = report.decision = "INSUFFICIENT_DATA"
        report.explanation_ar = "عدد الجلسات المكتملة أقل من الحد المطلوب لحساب الخطة."
    else:
        enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
        plan = TradePlanEngine.calculate_trade_plan(enriched, 0).get("trade_plan")
        report.levels = plan_levels(plan)
        breakout = BreakoutEntryAdvisor.evaluate(
            price, enriched, 0, owns_stock=bool(holding)
        )
        report.breakout = breakout.get("decision")
        if not report.levels and not holding and breakout.get("actionable"):
            report.levels = plan_levels(breakout)
        if report.levels and not holding:
            assess_entry(report, capital, cash)
        if (
            holding
            and capital
            and capital > 0
            and (request.source != "THNDR" or freshness == "REALTIME_VERIFIED")
        ):
            evaluated = LiveDecisionEngine.evaluate(
                security.ticker,
                price,
                capital,
                owns_stock=True,
                buy_price=holding.average_price,
                shares_owned=holding.quantity
                if request.source == "THNDR"
                else holding.shares,
                analytical_bars=enriched,
                sessions_behind=0,
            )
            report.decision = evaluated["decision"]
            report.signal = {
                "EXIT_STOP_LOSS": "STRONG_SELL",
                "TAKE_PROFIT": "SELL",
                "TAKE_PARTIAL_PROFIT": "SELL",
                "RAISE_STOP_LOSS": "HOLD",
                "HOLD": "HOLD",
            }.get(report.decision, "WAIT")
            report.explanation_ar = (
                "ده تقييم مشروط لإدارة المركز على السعر المرجعي المعروض."
            )
        elif holding:
            report.decision, report.signal = "WAIT_POSITION_DATA", "WAIT"
            report.explanation_ar = (
                "راجع سعر المركز وقيمة المحفظة قبل تقييم أي تعديل على المركز."
            )
        elif request.source == "THNDR":
            report.signal, report.decision, report.suggested_shares = (
                "WAIT",
                "WAIT_VERIFIED_QUOTE",
                None,
            )
            report.explanation_ar = (
                "تحليل ثاندر محتاج سعر موثّق ومركز مطابق قبل تقييم إدارة الصفقة."
            )
        if report.levels:
            report.horizon_ar = "الخطة تتراجع عند الجلسة المكتملة التالية، أو فور تغيّر السعر أو شروط الدخول."
            report.expires_at = now + timedelta(minutes=15)
            report.invalidation_ar = [
                "كسر وقف الخسارة",
                "تغير الجلسة المرجعية",
                "عدم تأكيد السعر والنطاق",
            ]
    if holding and identity_valid:
        report.position = position_review(
            request, holding, capital, cash, report, report.decision, plan
        )
    if not for_risk_review:
        apply_analysis_policy(db, security, report)
    add_evidence(report)
    return report


def assess_entry(report, capital, cash):
    levels, price = report.levels, report.price
    if price <= levels.stop:
        report.decision, report.explanation_ar = (
            "DO_NOT_ENTER",
            "السعر المرجعي كسر الوقف. الخطة اتلغت.",
        )
    elif price > levels.upper:
        report.signal, report.decision, report.explanation_ar = (
            "WAIT",
            "DO_NOT_CHASE",
            PHRASES[E.CHASING],
        )
    elif price < levels.lower:
        report.signal, report.decision, report.explanation_ar = (
            "WAIT",
            "NEAR_ENTRY",
            PHRASES[E.WAIT_ENTRY],
        )
    elif report.technical_rating in {"BUY", "STRONG_BUY"}:
        report.signal, report.decision, report.explanation_ar = (
            report.technical_rating,
            "CONDITIONAL_ENTRY",
            PHRASES[E.ENTRY_ZONE],
        )
        if capital and capital > 0:
            sizing = RiskManager.calculate_position_sizing(
                capital, levels.upper, levels.stop
            )
            report.suggested_shares = sizing["suggested_shares"]
            if cash is not None:
                report.suggested_shares = min(
                    report.suggested_shares, int(cash // levels.upper)
                )
            if report.suggested_shares == 0:
                report.signal = "WAIT"
                report.decision = "INSUFFICIENT_CAPACITY"
                report.explanation_ar = "الكاش أو حدود المخاطرة والتخصيص مش سامحة حتى بسهم واحد عند سعر الحساب."
    else:
        report.signal, report.decision, report.explanation_ar = (
            "WAIT",
            "WAIT_CONFIRMATION",
            PHRASES[E.WAIT_ENTRY],
        )


def add_evidence(report):
    supporting, opposing = report.supporting, report.opposing
    for value, positive, negative in (
        (report.trend_score, E.TREND_SUPPORT, E.TREND_WEAK),
        (report.momentum_score, E.MOMENTUM_SUPPORT, E.MOMENTUM_WEAK),
    ):
        if value is not None and value > 10:
            supporting.append(positive)
        elif value is not None and value < -10:
            opposing.append(negative)
    if (
        report.trend_score
        and report.momentum_score
        and report.trend_score * report.momentum_score < 0
    ):
        opposing.append(E.CONFLICT)
    if (report.relative_volume or 0) >= 1.25:
        supporting.append(E.VOLUME_SUPPORT)
    elif (report.relative_volume or 0) < 0.75:
        opposing.append(E.THIN_VOLUME)
    if report.levels and report.levels.lower <= report.price <= report.levels.upper:
        supporting.append(E.ENTRY_ZONE)
    if report.breakout in {"ENTER_BREAKOUT", "ADD_ON_BREAKOUT"}:
        supporting.append(E.BREAKOUT)
    if report.signal in {"SELL", "STRONG_SELL"}:
        opposing.append(E.EXIT_ZONE)
    if report.decision == "DO_NOT_CHASE":
        opposing.append(E.CHASING)
    if report.decision in {"WAIT_CONFIRMATION", "NEAR_ENTRY"}:
        opposing.append(E.WAIT_ENTRY)
    if report.signal in {"DATA_NOT_CURRENT", "INSUFFICIENT_DATA"}:
        opposing.append(E.STALE_DATA)
    if report.signal == "NO_TRADE":
        opposing.append(E.NO_SETUP)
    if (
        report.position
        and (report.position.exposure_pct or 0) >= 100 * settings.MAX_ALLOCATION_PCT
    ):
        opposing.append(E.EXPOSURE)
    if report.company_events:
        opposing.append(E.EVENT_RISK)
    opposing.extend((E.PRICE_UNVERIFIED, E.FUNDAMENTALS_MISSING))
    atr = report.volatility_pct
    if atr is not None and atr >= 5:
        opposing.append(E.VOLATILITY)
    if atr is not None:
        report.risk = (
            "HIGH"
            if atr >= 5 or E.EXPOSURE in opposing
            else "MODERATE"
            if atr >= 2
            else "LOW"
        )
    report.supporting_ar = [PHRASES[code] for code in supporting]
    report.opposing_ar = [PHRASES[code] for code in opposing]


def model_context(report):
    # No strings from external sources, no symbols/ISINs, no purchase price or balances.
    return {
        "supporting": [str(code) for code in report.supporting],
        "opposing": [str(code) for code in report.opposing],
        "signal": report.signal,
        "risk": report.risk,
        "freshness": report.freshness,
        "market_status": report.market_status,
        "position_action": report.position.action if report.position else None,
    }
