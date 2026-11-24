from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from app.schemas.thndr import Freshness, Ticker

Money = Annotated[FiniteFloat, Field(gt=0, le=1e12)]
Signal = Literal[
    "STRONG_BUY",
    "BUY",
    "HOLD",
    "WAIT",
    "SELL",
    "STRONG_SELL",
    "NO_TRADE",
    "DATA_NOT_CURRENT",
    "INSUFFICIENT_DATA",
]
PositionAction = Literal[
    "HOLD",
    "ADD_TO_POSITION",
    "PARTIAL_SELL",
    "FULL_EXIT",
    "MOVE_STOP_LOSS",
    "TAKE_PARTIAL_PROFIT",
    "WAIT",
]


class ManualPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shares: Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]
    average_price: Money


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Ticker
    manual_price: Money | None = None
    portfolio_value: Money | None = None
    cash: Annotated[FiniteFloat, Field(ge=0, le=1e12)] | None = None
    position: ManualPosition | None = None
    source: Literal["MANUAL", "THNDR"] = "MANUAL"
    explain: bool = True

    @model_validator(mode="after")
    def validate_source(self):
        if self.source == "THNDR" and any(
            v is not None
            for v in (self.position, self.portfolio_value, self.manual_price, self.cash)
        ):
            raise ValueError("Broker and manual inputs must be separate")
        if self.cash is not None and (
            self.portfolio_value is None or self.cash > self.portfolio_value
        ):
            raise ValueError("Invalid cash amount")
        return self


class EvidenceCode(StrEnum):
    TREND_SUPPORT = "TREND_SUPPORT"
    MOMENTUM_SUPPORT = "MOMENTUM_SUPPORT"
    VOLUME_SUPPORT = "VOLUME_SUPPORT"
    BREAKOUT = "BREAKOUT"
    ENTRY_ZONE = "ENTRY_ZONE"
    TREND_WEAK = "TREND_WEAK"
    MOMENTUM_WEAK = "MOMENTUM_WEAK"
    CONFLICT = "CONFLICT"
    THIN_VOLUME = "THIN_VOLUME"
    VOLATILITY = "VOLATILITY"
    CHASING = "CHASING"
    WAIT_ENTRY = "WAIT_ENTRY"
    EXIT_ZONE = "EXIT_ZONE"
    STALE_DATA = "STALE_DATA"
    PRICE_UNVERIFIED = "PRICE_UNVERIFIED"
    FUNDAMENTALS_MISSING = "FUNDAMENTALS_MISSING"
    EVENT_RISK = "EVENT_RISK"
    EXPOSURE = "EXPOSURE"
    NO_SETUP = "NO_SETUP"


class InterpretationSelection(BaseModel):
    """The model orders evidence from a closed vocabulary. It cannot supply prices or advice."""

    model_config = ConfigDict(extra="forbid")
    priority: list[EvidenceCode]


class PlanLevels(BaseModel):
    lower: float
    upper: float
    stop: float
    targets: tuple[float, float, float]
    reward_to_risk: tuple[float, float, float]
    support: float | None
    resistance: float | None


class PositionReview(BaseModel):
    source: Literal["MANUAL", "THNDR"]
    shares: float | None
    average_price: float | None
    unrealized_pnl: float | None
    exposure_pct: float | None
    action: PositionAction
    add_on_decision: str | None = None
    scenario_actions: list[PositionAction] = Field(default_factory=list)
    scenarios_ar: list[str] = Field(default_factory=list)


class Analysis(BaseModel):
    ticker: Ticker
    company: str
    sector: str
    signal: Signal
    decision: str
    explanation_ar: str
    executable: Literal[False] = False
    price: float | None
    provider: str | None
    price_timestamp: datetime | None = None
    reference_session: date | None = None
    freshness: Freshness
    market_status: Literal["OPEN", "CLOSED", "HALTED", "UNKNOWN"]
    technical_rating: str | None = None
    score: float | None = None
    agreement_pct: float | None = None
    trend_score: float | None = None
    momentum_score: float | None = None
    relative_volume: float | None = None
    mean_volume: float | None = None
    volatility_pct: float | None = None
    breakout: str | None = None
    levels: PlanLevels | None = None
    suggested_shares: int | None = None
    position: PositionReview | None = None
    risk: Literal["LOW", "MODERATE", "HIGH", "UNKNOWN"] = "UNKNOWN"
    horizon_ar: str | None = None
    expires_at: datetime | None = None
    invalidation_ar: list[str] = Field(default_factory=list)
    missing_ar: list[str] = Field(default_factory=list)
    supporting: list[EvidenceCode] = Field(default_factory=list)
    opposing: list[EvidenceCode] = Field(default_factory=list)
    supporting_ar: list[str] = Field(default_factory=list)
    opposing_ar: list[str] = Field(default_factory=list)
    company_events: list[dict[str, str]] = Field(default_factory=list)
    ai_status: str = "DETERMINISTIC_ONLY"
    ai_explanation_ar: str | None = None
    usage: dict[str, int | float] | None = None
