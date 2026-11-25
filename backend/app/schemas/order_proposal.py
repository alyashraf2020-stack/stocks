from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.risk import Positive
from app.schemas.thndr import Ticker

Intent = Literal[
    "BUY", "ADD", "PARTIAL_SELL", "FULL_EXIT", "TAKE_PROFIT", "STOP_REVIEW"
]
Source = Literal["ANALYSIS", "MANUAL", "THNDR"]
Price = Annotated[Positive, Field(le=Decimal(10000000))]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftRequest(Strict):
    key: UUID
    ticker: Ticker
    intent: Intent
    source: Source = "ANALYSIS"
    shares: Annotated[int, Field(strict=True, ge=1, le=1_000_000)] | None = None
    limit: Price | None = None


class TradingSettings(Strict):
    mode: Literal["ANALYSIS_ONLY", "PAPER_TRADING", "SEMI_AUTOMATIC_REVIEW"] = (
        "ANALYSIS_ONLY"
    )
    automatic_drafts: bool = False
    max_quote_age: int = Field(30, ge=5, le=60)
    max_adverse_move_bps: int = Field(25, ge=0, le=100)
    revision: int = Field(0, ge=0)


class ExactReview(Strict):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    understood: Literal[True]


class ReviewRequest(Strict):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
