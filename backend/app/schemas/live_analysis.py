from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.schemas.analysis import TradePlanResponse

class LiveAnalysisRequest(BaseModel):
    ticker: str = Field(..., description="EGX Stock Ticker, e.g. COMI")
    current_price: float = Field(..., gt=0, description="Manual current market price in EGP")
    capital: float = Field(..., gt=0, description="Total portfolio capital in EGP")
    owns_stock: bool = Field(False, description="True if the user already holds a position")
    buy_price: Optional[float] = Field(None, description="Purchase price in EGP if already owned")
    shares_owned: Optional[int] = Field(None, description="Number of shares held if already owned")

class PositionSizingResponse(BaseModel):
    capital: float
    planning_entry: float
    stop_loss: float
    risk_per_share: float
    max_risk_allowed_egp: float
    max_allocation_allowed_egp: float
    shares_by_risk: int
    shares_by_allocation: int
    suggested_shares: int
    position_value_egp: float
    max_expected_loss_egp: float
    actual_risk_pct: float
    actual_allocation_pct: float

class LiveAnalysisResponse(BaseModel):
    ticker: str
    current_price: float
    decision: str
    decision_ar: str
    badge_color: str
    actionable_new_trade: bool
    current_analysis_eligible: bool
    reason_ar: str
    owns_stock: Optional[bool] = False
    buy_price: Optional[float] = None
    shares_owned: Optional[int] = None
    expected_latest_session: Optional[str] = None
    latest_available_session: Optional[str] = None
    latest_close: Optional[float] = None
    sessions_behind: Optional[int] = None
    freshness_ar: Optional[str] = None
    actual_provider: Optional[str] = None
    analytical_bars_count: Optional[int] = None
    plan_status: Optional[str] = None
    new_entry_allowed: Optional[bool] = None
    status: str
    trade_plan: Optional[TradePlanResponse] = None
    previous_plan: Optional[TradePlanResponse] = None
    position_sizing: Optional[PositionSizingResponse] = None