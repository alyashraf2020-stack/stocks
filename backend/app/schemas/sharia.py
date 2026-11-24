from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator

from app.schemas.risk import Amount, Positive

ScreenStatus = Literal["COMPLIANT", "NON_COMPLIANT", "UNVERIFIED"]
METHOD = "EGX33-2025-08-STRICT"
METHOD_URL = "https://beta.egx.com.eg/api/media/uploads/EGX_33_Shariah_Index_4_aug_2025_3ee293dea8.pdf"
INDEX_URL = "https://beta.egx.com.eg/ar/market/indices/constituents?index=EGX_SHARIAH"


class ScreeningEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_on: date
    activity: Literal["PERMITTED", "PROHIBITED", "UNKNOWN"]
    activity_source: HttpUrl
    ordinary_share: bool | None = None
    period_end: date | None = None
    financial_source: HttpUrl | None = None
    market_value_source: HttpUrl | None = None
    total_revenue: Positive | None = None
    noncompliant_income: Amount | None = None
    total_assets: Positive | None = None
    average_market_value: Positive | None = None
    interest_debt: Amount | None = None
    interest_investments: Amount | None = None
    liquid_assets: Amount | None = None
    index_member: bool | None = None
    index_as_of: date | None = None
    index_source: HttpUrl | None = None

    @model_validator(mode="after")
    def consistent_evidence(self):
        if self.period_end and self.period_end > self.reviewed_on:
            raise ValueError("Financial period ends after review")
        if self.index_member is not None and (
            not self.index_as_of or not self.index_source
        ):
            raise ValueError("Membership needs a dated source")
        if self.index_as_of and self.index_as_of > self.reviewed_on:
            raise ValueError("Index date is after review")
        if (
            self.liquid_assets is not None
            and self.total_assets
            and self.liquid_assets > self.total_assets
        ):
            raise ValueError("Liquid assets cannot exceed total assets")
        for url in (
            self.activity_source,
            self.financial_source,
            self.market_value_source,
            self.index_source,
        ):
            if url and (
                url.scheme != "https"
                or url.username is not None
                or url.password is not None
            ):
                raise ValueError("Source must be a public HTTPS document")
        return self
