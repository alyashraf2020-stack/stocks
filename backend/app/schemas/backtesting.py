from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.paper_trading import Execution, Price, Strategy, StrictModel
from app.schemas.risk import Positive, RiskPolicy
from app.schemas.thndr import Ticker


class DailyBar(StrictModel):
    day: date
    available_at: AwareDatetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int = Field(ge=0, le=100_000_000_000)
    tick: Price | None = None
    lower_limit: Price | None = None
    upper_limit: Price | None = None
    opening_bid: Price | None = None
    opening_ask: Price | None = None

    @model_validator(mode="after")
    def geometry(self) -> Self:
        if (
            not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("Invalid OHLC geometry")
        if (self.opening_bid is None) != (self.opening_ask is None):
            raise ValueError("Opening quotes require both sides")
        if (
            self.opening_bid
            and not self.low <= self.opening_bid <= self.opening_ask <= self.high
        ):
            raise ValueError("Opening spread outside bar")
        return self


class Action(StrictModel):
    kind: Literal["SPLIT", "BONUS", "DIVIDEND", "OTHER"]
    day: date
    announced_at: AwareDatetime
    ratio: Positive | None = None
    cash_per_share: Positive | None = None
    payable_on: date | None = None

    @model_validator(mode="after")
    def terms(self) -> Self:
        if self.kind in {"SPLIT", "BONUS"} and self.ratio is None:
            raise ValueError("Missing split or bonus ratio")
        if self.kind == "DIVIDEND" and (
            not self.cash_per_share or not self.payable_on or self.payable_on < self.day
        ):
            raise ValueError("Missing dividend terms")
        return self


class DatasetUpload(StrictModel):
    ticker: Ticker
    isin: str | None = Field(default=None, pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    kind: Literal["EQUITY", "PRICE_INDEX", "TOTAL_RETURN_INDEX"]
    currency: Literal["EGP"]
    exchange: Literal["EGX"]
    source: str = Field(min_length=3, max_length=160)
    reference: str = Field(min_length=4, max_length=500)
    rights_confirmed: Literal[True]
    actions_reviewed: Literal[True]
    basis: Literal["UNADJUSTED", "INDEX_LEVEL"]
    listed_on: date
    delisted_on: date | None = None
    first_session: date
    last_session: date
    bars: list[DailyBar] = Field(min_length=1, max_length=420)
    actions: list[Action] = Field(default_factory=list, max_length=50)
    suspended: list[date] = Field(default_factory=list, max_length=100)


class BacktestRequest(StrictModel):
    datasets: list[UUID] = Field(default_factory=list, max_length=15)
    tickers: list[Ticker] = Field(default_factory=list, max_length=15)
    watchlist: bool = False
    strategies: list[Strategy] = Field(min_length=1, max_length=5)
    start: date
    end: date
    capital: Annotated[Positive, Field(ge=1, le=100_000_000)]
    execution: Execution
    risk: RiskPolicy | None = None
    benchmark: UUID | None = None
    robustness: Literal["NONE", "SPLIT", "WALK_FORWARD", "STRESS"] = "NONE"
    seed: int = Field(default=42, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def range_and_lists(self) -> Self:
        if not 1 <= (self.end - self.start).days <= 365:
            raise ValueError("Use a chronological date range up to 366 calendar days")
        for values in (self.datasets, self.tickers, self.strategies):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate item")
        if not (self.datasets or self.tickers or self.watchlist):
            raise ValueError(
                "Select instruments, approved datasets or the saved watchlist"
            )
        return self
