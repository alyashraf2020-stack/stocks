from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.thndr import Ticker

D = Decimal
Amount = Annotated[Decimal, Field(ge=0, le=D("1e14"), max_digits=22, decimal_places=6)]
Positive = Annotated[
    Decimal, Field(gt=0, le=D("1e14"), max_digits=22, decimal_places=6)
]
Fraction = Annotated[Decimal, Field(gt=0, le=1)]
CostRate = Annotated[Decimal, Field(ge=0, le=D(".2"))]


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advanced_enabled: bool = False
    islamic_mode: bool = False
    kill_switch: bool = False
    max_trade_risk: Decimal = Field(D(".015"), gt=0, le=D(".015"))
    max_stock_allocation: Decimal = Field(D(".20"), gt=0, le=D(".20"))
    max_total_exposure: Fraction = D(".80")
    max_sector_exposure: Fraction = D(".30")
    max_daily_loss: Fraction = D(".03")
    max_drawdown: Fraction = D(".10")
    max_open_positions: int = Field(10, strict=True, ge=1, le=200)
    max_aggregate_risk: Fraction = D(".06")
    min_reward_to_risk: Decimal = Field(D("1.5"), gt=0, le=100)
    min_daily_turnover: Amount = D("1000000")
    commission_rate: CostRate | None = None
    buy_tax_rate: CostRate | None = None
    sell_tax_rate: CostRate | None = None
    slippage_rate: CostRate = D(".005")
    stop_gap_rate: CostRate = D(".02")
    max_snapshot_minutes: int = Field(30, strict=True, ge=1, le=120)

    @property
    def advanced_required(self):
        return (
            self.advanced_enabled
            or self.max_trade_risk < D(".015")
            or self.max_stock_allocation < D(".20")
        )


class RiskPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Ticker
    shares: Positive | None = None
    mark: Positive | None = None
    reported_value: Amount | None = None
    average_cost: Positive | None = None
    stop: Positive | None = None
    sellable_shares: Amount | None = None

    @model_validator(mode="after")
    def settled_shares(self):
        if self.sellable_shares is not None and (
            self.shares is None or self.sellable_shares > self.shares
        ):
            raise ValueError("Sellable shares cannot exceed shares held")
        return self


class PendingBuy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Ticker
    reserved_cash: Amount | None = None
    notional: Positive | None = None
    planned_risk: Amount | None = None

    @model_validator(mode="after")
    def reserve_covers_order(self):
        if (
            self.notional is not None
            and self.reserved_cash is not None
            and self.reserved_cash < self.notional
        ):
            raise ValueError("Cash reserved for a buy cannot be below its notional")
        return self


class EquityPoint(BaseModel):
    day: date
    equity: Positive


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareDatetime | None = None
    equity: Positive | None = None
    settled_cash: Amount | None = None
    buying_power: Amount | None = None
    positions: list[RiskPosition] | None = Field(None, max_length=300)
    pending_buys: list[PendingBuy] | None = Field(None, max_length=300)
    # Owner-reviewed, externally flow-adjusted closing equity on actual valuation dates.
    adjusted_history: list[EquityPoint] | None = Field(None, max_length=400)
    adjusted_equity_now: Positive | None = None

    @model_validator(mode="after")
    def unique_inputs(self):
        symbols = [p.ticker for p in self.positions or []]
        days = [p.day for p in self.adjusted_history or []]
        if len(set(symbols)) != len(symbols) or len(set(days)) != len(days):
            raise ValueError("Duplicate position or valuation date")
        return self


class Candidate(BaseModel):
    ticker: Ticker
    entry: Positive
    stop: Positive
    target: Positive
    average_turnover: Amount | None = None

    @model_validator(mode="after")
    def price_geometry(self):
        if not self.stop < self.entry < self.target:
            raise ValueError("Expected stop < entry < target")
        return self


class ScenarioRequest(BaseModel):
    ticker: Ticker
    action: Literal[
        "HOLD",
        "ADD_TO_POSITION",
        "PARTIAL_SELL",
        "FULL_EXIT",
        "MOVE_STOP_LOSS",
        "TAKE_PARTIAL_PROFIT",
        "WAIT",
    ]
    shares: Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)] | None = None
    revised_stop: Positive | None = None


class RiskReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["MANUAL", "THNDR"] = "MANUAL"
    manual: PortfolioSnapshot | None = None
    candidate_ticker: Ticker | None = None
    scenario: ScenarioRequest | None = None

    @model_validator(mode="after")
    def consistent_source(self):
        if self.source == "THNDR" and self.manual is not None:
            raise ValueError("Manual data cannot be merged into a brokerage snapshot")
        return self
