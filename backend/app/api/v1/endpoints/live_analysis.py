from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.live_analysis import (
    LiveAnalysisRequest,
    LiveAnalysisResponse,
    ManualEODRequest,
    ManualEODResponse,
)
from app.services.security_master import SecurityMasterService
from app.services.data_provider.manager import default_provider_manager
from app.services.indicators import TechnicalIndicatorEngine
from app.services.decision_engine import LiveDecisionEngine
from app.services.owner_add_on import OwnerAddOnAdvisor
from app.services.corporate_events import CorporateEventService
from app.services.market_depth import MarketDepthService
from app.services.breakout_entry import BreakoutEntryAdvisor
from app.services.validator import CandleValidator
from app.models.candle import EGXCandle

router = APIRouter()


@router.post("/manual-eod", response_model=ManualEODResponse)
def save_manual_eod(req: ManualEODRequest, db: Session = Depends(get_db)):
    sec = SecurityMasterService.get_by_ticker(db, req.ticker)
    if not sec:
        raise HTTPException(status_code=400, detail="السهم غير مدرج في البورصة المصرية.")

    data_res = default_provider_manager.get_analytical_bars(
        sec.ticker,
        limit=250,
        db=db,
        force_refresh=True,
    )

    expected_session = data_res.get("expected_latest_session")
    if not expected_session:
        raise HTTPException(status_code=400, detail="تعذر تحديد آخر جلسة مكتملة متوقعة.")

    if data_res.get("sessions_behind") == 0:
        raise HTTPException(
            status_code=400,
            detail="البيانات محدثة بالفعل ولا تحتاج إدخال جلسة يدويًا.",
        )

    if req.session_date != expected_session:
        raise HTTPException(
            status_code=400,
            detail=f"يجب أن تكون الجلسة المدخلة هي الجلسة المتوقعة بالضبط: {expected_session}",
        )

    raw_bar = {
        "ticker": sec.ticker,
        "session_date": req.session_date,
        "open": req.open,
        "high": req.high,
        "low": req.low,
        "close": req.close,
        "volume": req.volume,
        "actual_provider": "USER_VERIFIED_EOD",
    }
    validated = CandleValidator.validate_bar(raw_bar)

    # Some broker screens can publish an Open/reference value that sits slightly
    # outside the reported High/Low range. Preserve that value exactly instead of
    # fabricating a replacement. The technical engine uses validated HLCV for its
    # indicators, so an unverified Open is allowed as long as HLCV itself is valid.
    if validated.get("hlcv_status") != "VALID" or validated.get("open_status") == "INVALID_OPEN":
        raise HTTPException(
            status_code=400,
            detail=(
                "بيانات الجلسة غير منطقية. يجب أن يكون High >= Low، وأن يقع Close بينهما، "
                "وأن تكون الأسعار موجبة والحجم غير سالب. يمكن قبول Open الموجب خارج النطاق "
                "كقيمة مرجعية غير موثوقة ولن يعتمد عليه التحليل الفني."
            ),
        )

    existing = (
        db.query(EGXCandle)
        .filter(
            EGXCandle.ticker == sec.ticker,
            EGXCandle.session_date == req.session_date,
        )
        .first()
    )

    if existing and existing.actual_provider != "USER_VERIFIED_EOD":
        raise HTTPException(
            status_code=409,
            detail="توجد بالفعل جلسة محفوظة من مزود بيانات لهذا التاريخ، ولن يتم استبدالها يدويًا.",
        )

    if existing:
        existing.open = req.open
        existing.high = req.high
        existing.low = req.low
        existing.close = req.close
        existing.volume = req.volume
        existing.actual_provider = "USER_VERIFIED_EOD"
        existing.validation_status = validated["validation_status"]
    else:
        db.add(
            EGXCandle(
                ticker=sec.ticker,
                session_date=req.session_date,
                open=req.open,
                high=req.high,
                low=req.low,
                close=req.close,
                volume=req.volume,
                actual_provider="USER_VERIFIED_EOD",
                validation_status=validated["validation_status"],
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="تعذر حفظ بيانات الجلسة يدويًا.")

    if validated.get("open_status") == "RAW_OPEN":
        message_ar = "تم حفظ الجلسة المدخلة يدويًا والتحقق من OHLCV. أعد التحليل الآن."
    else:
        message_ar = (
            "تم حفظ الجلسة والتحقق من High/Low/Close/Volume. قيمة Open من الوسيط محفوظة "
            "كمرجع غير موثوق لأنها خارج نطاق الجلسة، ولن يعتمد عليها التحليل الفني."
        )

    return {
        "status": "SUCCESS",
        "ticker": sec.ticker,
        "session_date": req.session_date,
        "actual_provider": "USER_VERIFIED_EOD",
        "message_ar": message_ar,
    }


@router.post("", response_model=LiveAnalysisResponse)
def analyze_live_price(req: LiveAnalysisRequest, db: Session = Depends(get_db)):
    # 1. Verify ticker belongs to Egyptian Exchange Security Master
    sec = SecurityMasterService.get_by_ticker(db, req.ticker)
    if not sec:
        raise HTTPException(
            status_code=400,
            detail=f"السهم '{req.ticker}' غير مدرج في البورصة المصرية. المنصة تدعم أسهم البورصة المصرية فقط."
        )

    # 2. Fetch analytical historical data
    data_res = default_provider_manager.get_analytical_bars(sec.ticker, limit=250, db=db)
    raw_bars = data_res.get("bars", [])

    # 3. Compute indicators on historical data
    enriched_bars = TechnicalIndicatorEngine.compute_all_indicators(raw_bars) if raw_bars else []

    # 4. Run Decision Engine with strict Zero-Lag Policy
    decision_result = LiveDecisionEngine.evaluate(
        ticker=sec.ticker,
        current_price=req.current_price,
        capital=req.capital,
        owns_stock=req.owns_stock,
        buy_price=req.buy_price,
        shares_owned=req.shares_owned,
        analytical_bars=enriched_bars,
        sessions_behind=data_res.get("sessions_behind"),
        expected_latest_session=data_res.get("expected_latest_session"),
        latest_available_session=data_res.get("latest_session"),
        actual_provider=data_res.get("actual_provider")
    )

    # 5. Existing holders get a SEPARATE pullback/add-on decision. This does not
    # alter the main position-management decision (hold / take profit / exit).
    owner_add_on = None
    if req.owns_stock:
        owner_add_on = OwnerAddOnAdvisor.evaluate(
            current_price=req.current_price,
            capital=req.capital,
            shares_owned=req.shares_owned,
            trade_plan=decision_result.get("trade_plan"),
            sessions_behind=data_res.get("sessions_behind"),
        )

    # 6. Verified corporate events are context only; they never force a buy signal.
    corporate_events = CorporateEventService.get_relevant_events(sec.ticker)

    # 7. Market depth is optional context. No order-book data is fabricated.
    market_depth = MarketDepthService.summarize(
        bid_depth_qty=req.bid_depth_qty,
        ask_depth_qty=req.ask_depth_qty,
    )

    # 8. Alternative breakout scenario: answers "what if the stock never pulls back?"
    # Levels are calculated only from completed EOD bars; manual live price is used
    # solely to compare against those levels.
    breakout_entry = BreakoutEntryAdvisor.evaluate(
        current_price=req.current_price,
        analytical_bars=enriched_bars,
        sessions_behind=data_res.get("sessions_behind"),
        owns_stock=req.owns_stock,
        market_depth=market_depth,
    )

    # For non-owners, when the pullback engine has no current setup, surface the
    # breakout path as the primary live answer so the UI does not simply say
    # "no valid setup" without telling the user what level to watch.
    if (
        not req.owns_stock
        and decision_result.get("decision") == "NO_VALID_SETUP"
        and breakout_entry.get("status") == "VALID"
    ):
        decision_result["decision"] = breakout_entry["decision"]
        decision_result["decision_ar"] = breakout_entry["decision_ar"]
        decision_result["reason_ar"] = breakout_entry["reason_ar"]
        decision_result["actionable_new_trade"] = bool(breakout_entry.get("actionable", False))
        decision_result["badge_color"] = "green" if breakout_entry.get("actionable") else "amber"

    decision_result["owner_add_on"] = owner_add_on
    decision_result["corporate_events"] = corporate_events
    decision_result["market_depth"] = market_depth
    decision_result["breakout_entry"] = breakout_entry

    return decision_result
