from typing import Dict, List, Optional
from pydantic import BaseModel


class IndicatorVote(BaseModel):
    key: str
    group: str
    value: Optional[float] = None
    vote: Optional[int] = None
    signal: str
    rule_ar: str


class TechnicalRatingResponse(BaseModel):
    methodology: str
    status: str
    as_of_session: str
    is_current: bool
    score: float
    signal: str
    signal_ar: str
    available_count: int
    total_count: int
    coverage_pct: float
    agreement_pct: float
    counts: Dict[str, int]
    trend_score: float
    momentum_score: float
    daily_change: float
    daily_change_pct: float
    daily_reference_session: str
    atr_pct: float
    volatility_ar: str
    mean_volume_20: float
    relative_volume: Optional[float] = None
    indicators: List[IndicatorVote]
    note_ar: str


class PlanMetricsResponse(BaseModel):
    reference_entry: float
    risk_per_share: float
    risk_pct: float
    target_gain_pct: List[float]
    reward_risk: List[float]
