from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.live_analysis import LiveAnalysisRequest, LiveAnalysisResponse
from app.services.security_master import SecurityMasterService
from app.services.data_provider.manager import default_provider_manager
from app.services.indicators import TechnicalIndicatorEngine
from app.services.decision_engine import LiveDecisionEngine
from app.services.owner_add_on import OwnerAddOnAdvisor
from app.services.corporate_events import CorporateEventService
from app.services.market_depth import MarketDepthService
from app.services.breakout_entry import BreakoutEntryAdvisor

router = APIRouter()


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
