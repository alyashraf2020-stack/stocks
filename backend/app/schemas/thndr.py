"""Only these projected brokerage fields can cross the API boundary."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)

Freshness = Literal[
    "REALTIME_VERIFIED", "DELAYED", "HISTORICAL", "MANUAL", "STALE", "UNKNOWN"
]
Amount = Annotated[FiniteFloat, Field(ge=0)]
Ticker = Annotated[str, Field(pattern=r"^[A-Z0-9._-]{1,20}$")]


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ticker: Ticker
    instrument_id: str
    exchange: str
    currency: str
    price: Annotated[FiniteFloat, Field(gt=0)]
    source_timestamp: AwareDatetime | None
    retrieved_at: AwareDatetime
    provider: str
    delay_class: Literal["REALTIME", "DELAYED", "HISTORICAL", "MANUAL", "UNKNOWN"]
    session_status: Literal["OPEN", "CLOSED", "HALTED", "UNKNOWN"]


class CheckedQuote(Quote):
    freshness: Freshness
    validation_status: Literal["VALID", "INVALID", "UNVERIFIED"]
    eligible_for_proposal: bool


class Holding(BaseModel):
    ticker: Ticker
    instrument_id: str | None = None
    quantity: Amount | None = None
    average_price: Amount | None = None
    market_value: Amount | None = None
    unrealized_pnl: FiniteFloat | None = None
    quote: CheckedQuote | None = None


class AccountItem(BaseModel):
    """Project records without returning raw broker metadata or account identifiers."""

    kind: str | None = Field(None, max_length=80)
    ticker: Ticker | None = None
    status: str | None = Field(None, max_length=60)
    timestamp: AwareDatetime | None = None
    amount: FiniteFloat | None = None
    quantity: Amount | None = None

    @model_validator(mode="after")
    def meaningful(self):
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("Unrecognized account record")
        return self


class AccountInfo(BaseModel):
    registration_status: str | None = Field(None, max_length=80)
    eligible_for_egx: bool | None = None
    deposits_enabled: bool | None = None
    withdrawals_enabled: bool | None = None

    @model_validator(mode="after")
    def meaningful(self):
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("Unrecognized account information")
        return self


class Portfolio(BaseModel):
    account: AccountInfo | None = None
    currency: Literal["EGP"] | None = None
    available_cash: Amount | None = None
    invested_amount: Amount | None = None
    total_value: Amount | None = None
    realized_pnl: FiniteFloat | None = None
    unrealized_pnl: FiniteFloat | None = None
    holdings: list[Holding] | None = None
    transactions: list[AccountItem] | None = None
    open_orders: list[AccountItem] | None = None
    watchlist: list[Ticker] | None = None
    market_status: Literal["OPEN", "CLOSED", "HALTED", "UNKNOWN"] = "UNKNOWN"
    last_sync: AwareDatetime | None = None
    issues: dict[str, str] = Field(default_factory=dict)


class Connection(BaseModel):
    status: Literal[
        "NOT_CONFIGURED",
        "DISCONNECTED",
        "AUTHORIZING",
        "CONNECTED",
        "RECONNECT_REQUIRED",
        "REVOCATION_PENDING",
    ]
    permissions: list[str] = Field(default_factory=list)
    available: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    last_sync: datetime | None = None
    error: str | None = None
    freshness: Freshness = "UNKNOWN"
