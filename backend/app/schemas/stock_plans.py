from typing import List, Optional
from pydantic import BaseModel
from app.schemas.analysis import TradePlanResponse
from app.schemas.live_analysis import BreakoutEntryResponse


class StockPlanResponse(BaseModel):
    ticker: str
    arabic_name: str
    english_name: str
    sector: str
    listing_status: str
    status: str
    status_ar: str
    reason_ar: str
    expected_latest_session: str
    latest_available_session: Optional[str] = None
    latest_close: Optional[float] = None
    sessions_behind: Optional[int] = None
    actual_provider: Optional[str] = None
    analytical_bars_count: int = 0
    generated_at: str
    price_basis: str = "LAST_COMPLETED_SESSION_CLOSE"
    pullback_status_ar: Optional[str] = None
    trade_plan: Optional[TradePlanResponse] = None
    breakout_entry: Optional[BreakoutEntryResponse] = None


class StockPlansResponse(BaseModel):
    total: int
    expected_latest_session: str
    generated_at: str
    items: List[StockPlanResponse]
