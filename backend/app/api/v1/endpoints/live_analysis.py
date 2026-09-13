from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.live_analysis import LiveAnalysisRequest, LiveAnalysisResponse
from app.services.security_master import SecurityMasterService
from app.services.data_provider.manager import default_provider_manager
from app.services.indicators import TechnicalIndicatorEngine
from app.services.decision_engine import LiveDecisionEngine

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

    return decision_result