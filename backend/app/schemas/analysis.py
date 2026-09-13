from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class CandleBarResponse(BaseModel):
    session_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    actual_provider: str
    validation_status: str
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi_14: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_bandwidth: Optional[float] = None
    atr_14: Optional[float] = None

class ChartResponse(BaseModel):
    ticker: str
    range_selected: str
    total_bars: int
    expected_latest_session: str
    latest_available_session: Optional[str] = None
    latest_close: Optional[float] = None
    sessions_behind: Optional[int] = None
    freshness: str
    freshness_ar: str
    actual_provider: Optional[str] = None
    bars: List[CandleBarResponse]

class TradePlanResponse(BaseModel):
    entry_zone_min: Optional[float] = None
    entry_zone_max: Optional[float] = None
    planning_entry: Optional[float] = None
    stop_loss: Optional[float] = None
    r_unit: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    entry_basis: Optional[str] = None
    stop_basis: Optional[str] = None
    factor_score: Optional[int] = None
    analysis_strength: Optional[str] = None
    factor_breakdown: Optional[Dict[str, int]] = None
    plan_status: Optional[str] = None
    new_entry_allowed: Optional[bool] = None
    trigger_condition: Optional[str] = None