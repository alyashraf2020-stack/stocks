from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.risk import Amount, CostRate, Positive
from app.schemas.thndr import Ticker

Shares = Annotated[int, Field(strict=True, gt=0, le=100_000_000)]
Strategy = Literal["EGX26", "PULLBACK", "BREAKOUT", "TREND", "COMBINED"]
Side = Literal["BUY", "SELL"]
OrderKind = Literal["MARKET", "LIMIT", "STOP", "TARGET"]
OrderStatus = Literal[
    "PENDING",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "EXPIRED",
    "REJECTED",
]
Price = Annotated[Positive, Field(le=1_000_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Execution(StrictModel):
    commission_rate: CostRate
    buy_tax_rate: CostRate
    sell_tax_rate: CostRate
    charges_rate: CostRate
    fixed_fee: Amount
    minimum_commission: Amount
    slippage_rate: CostRate
    spread_rate: CostRate
    participation: Annotated[Decimal, Field(gt=0, le=Decimal(".10"))]
    settlement_sessions: Literal[2] = 2
    assumptions_source: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def bounded_rates(self) -> Self:
        if self.commission_rate + self.charges_rate + max(
            self.buy_tax_rate, self.sell_tax_rate
        ) > Decimal(".2"):
            raise ValueError("Combined fees must not exceed 20%")
        if self.slippage_rate + self.spread_rate / 2 > Decimal(".2"):
            raise ValueError("Combined price friction must not exceed 20%")
        return self


class AccountCreate(StrictModel):
    key: UUID
    name: str = Field(min_length=1, max_length=60, pattern=r"^\S.*$")
    capital: Annotated[Positive, Field(ge=1, le=100_000_000)]
    execution: Execution
    datasets: list[UUID] = Field(min_length=1, max_length=15)
    strategy: Strategy = "COMBINED"


class AccountControl(StrictModel):
    automated: bool
    strategy: Strategy
    datasets: list[UUID] | None = Field(default=None, min_length=1, max_length=15)


class CashRequest(StrictModel):
    key: UUID
    amount: Positive
    kind: Literal["DEPOSIT", "WITHDRAWAL"]


class OrderRequest(StrictModel):
    key: UUID
    ticker: Ticker
    side: Side
    kind: OrderKind
    shares: Shares
    limit: Price | None = None
    trigger: Price | None = None
    stop: Price | None = None
    target: Price | None = None
    expires_sessions: int = Field(default=3, ge=1, le=20)

    @model_validator(mode="after")
    def geometry(self) -> Self:
        if (self.kind == "LIMIT") != (self.limit is not None):
            raise ValueError("Limit price is required only for limit orders")
        if (self.kind in {"STOP", "TARGET"}) != (self.trigger is not None):
            raise ValueError("A trigger is required only for conditional exits")
        if self.side == "BUY" and (
            self.trigger or not self.stop or not self.target or self.stop >= self.target
        ):
            raise ValueError("Entry requires a stop and a higher target")
        if self.side == "SELL" and (self.stop or self.target):
            raise ValueError("Exit orders use only the selected execution condition")
        return self


class Order(StrictModel):
    id: str
    request: OrderRequest
    decision_session: date
    created: AwareDatetime
    eligible: date
    expires: date
    status: OrderStatus = "PENDING"
    filled: int = 0
    notional: Decimal = Decimal(0)
    reservation: Decimal = Decimal(0)
    entry_cap: Decimal | None = None
    risk_unit: Decimal = Decimal(0)
    mandatory: bool = False
    triggered: bool = False
    reason: str | None = None
    evidence: dict = Field(default_factory=dict)

    @property
    def remaining(self):
        return self.request.shares - self.filled

    @property
    def open(self):
        return self.status in {"PENDING", "ACCEPTED", "PARTIALLY_FILLED"}


class Settlement(StrictModel):
    available: date | None
    amount: Decimal


class Position(StrictModel):
    isin: str
    cost: Decimal
    settled: int = 0
    unsettled: list[Settlement] = Field(default_factory=list)
    stop: Decimal
    target: Decimal
    opened: date
    protection_created: AwareDatetime | None = None
    strategy: str

    @property
    def shares(self):
        return self.settled + sum(int(lot.amount) for lot in self.unsettled)


class Book(StrictModel):
    settled_cash: Decimal
    units: Decimal
    positions: dict[str, Position] = Field(default_factory=dict)
    proceeds: list[Settlement] = Field(default_factory=list)
    realized: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    taxes: Decimal = Decimal(0)
    history: list[dict] = Field(default_factory=list)
    marks: dict[str, Decimal] = Field(default_factory=dict)
    cursor: date | None = None
