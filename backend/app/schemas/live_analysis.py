from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from app.schemas.analysis import TradePlanResponse


class LiveAnalysisRequest(BaseModel):
    ticker: str = Field(..., description="EGX Stock Ticker, e.g. COMI")
    current_price: float = Field(..., gt=0, allow_inf_nan=False, description="Manual current market price in EGP")
    capital: float = Field(..., gt=0, allow_inf_nan=False, description="Total portfolio value including holdings and cash in EGP")
    owns_stock: bool = Field(False, description="True if the user already holds a position")
    buy_price: Optional[float] = Field(None, gt=0, allow_inf_nan=False, description="Purchase price in EGP if already owned")
    shares_owned: Optional[int] = Field(None, ge=1, strict=True, description="Number of shares held if already owned")
    add_on_cash: Optional[float] = Field(None, ge=0, allow_inf_nan=False, description="Cash available for this add-on, included in total portfolio value")
    bid_depth_qty: Optional[float] = Field(None, ge=0, description="Optional total buy-side depth from broker screen")
    ask_depth_qty: Optional[float] = Field(None, ge=0, description="Optional total sell-side depth from broker screen")

    @model_validator(mode="after")
    def cash_within_portfolio(self):
        if self.add_on_cash is not None and self.add_on_cash > self.capital:
            raise ValueError("مبلغ التعزيز لا يتجاوز إجمالي قيمة المحفظة؛ أضف أي إيداع جديد إلى إجمالي المحفظة أولًا.")
        return self


class ManualEODRequest(BaseModel):
    ticker: str = Field(..., description="EGX ticker")
    session_date: str = Field(..., description="Completed EGX session date in YYYY-MM-DD")
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)


class ManualEODResponse(BaseModel):
    status: str
    ticker: str
    session_date: str
    actual_provider: str
    message_ar: str


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


class OwnerAddOnSizingResponse(BaseModel):
    current_position_value_egp: float
    max_total_allocation_egp: float
    remaining_allocation_egp: float
    existing_risk_to_stop_egp: float
    remaining_risk_budget_egp: float
    suggested_add_on_shares: int
    estimated_add_on_value_egp: float
    portfolio_capital_egp: float
    available_add_on_cash_egp: Optional[float] = None
    cash_constraint_applied: bool
    sizing_price: float
    sizing_price_basis: str
    valuation_price: float
    reserved_position_value_egp: float
    max_allocation_pct: float
    max_risk_pct: float
    max_risk_allowed_egp: float
    risk_per_added_share_egp: float
    shares_by_allocation: int
    shares_by_risk: int
    shares_by_cash: Optional[int] = None
    limiting_factors: List[str]
    shares_after_add_on: int
    average_buy_price_after_add_on: Optional[float] = None
    remaining_cash_after_add_on_egp: Optional[float] = None
    position_value_after_add_on_egp: float
    risk_to_stop_after_add_on_egp: float
    executable_add_on_shares: int


class OwnerAddOnResponse(BaseModel):
    decision: str
    decision_ar: str
    reason_ar: str
    entry_zone_min: Optional[float] = None
    entry_zone_max: Optional[float] = None
    sizing: Optional[OwnerAddOnSizingResponse] = None


class CorporateEventResponse(BaseModel):
    event_type: str
    event_date: str
    title_ar: str
    summary_ar: str
    impact_bias: str
    source_name: str
    source_url: str
    days_to_event: int


class MarketDepthResponse(BaseModel):
    status: str
    source: Optional[str] = None
    buy_qty: Optional[float] = None
    sell_qty: Optional[float] = None
    imbalance_pct: Optional[float] = None
    pressure: str
    pressure_ar: str
    note_ar: str


class BreakoutEntryResponse(BaseModel):
    status: str
    decision: str
    decision_ar: str
    reason_ar: str
    actionable: bool
    resistance_level: Optional[float] = None
    trigger_price: Optional[float] = None
    entry_zone_min: Optional[float] = None
    entry_zone_max: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    confirmation_ar: Optional[str] = None
    uses_manual_price_for_levels: bool = False


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
    owner_add_on: Optional[OwnerAddOnResponse] = None
    corporate_events: List[CorporateEventResponse] = Field(default_factory=list)
    market_depth: Optional[MarketDepthResponse] = None
    breakout_entry: Optional[BreakoutEntryResponse] = None
