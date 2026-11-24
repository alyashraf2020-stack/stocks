from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.risk import PortfolioSnapshot
from app.schemas.thndr import Ticker

Mode = Literal["MARKET", "WATCHLIST", "MANUAL_PORTFOLIO", "THNDR_PORTFOLIO"]
INTERVALS = {60, 300, 900, 1800}


class ScannerEnvironment(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)
    SCANNER_ENABLED: bool = False
    SCANNER_INTERVAL_SECONDS: Literal[0, 60, 300, 900, 1800] = 0
    SCANNER_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=4)
    SCANNER_MAX_SYMBOLS_PER_SCAN: int = Field(default=500, ge=1, le=1000)
    SCANNER_AI_ENABLED: bool = False
    SCANNER_MAX_AI_REQUESTS_PER_SCAN: int = Field(default=2, ge=0, le=5)
    SCANNER_LEASE_SECONDS: int = Field(default=60, ge=15, le=600)
    SCANNER_HEARTBEAT_SECONDS: int = Field(default=5, ge=1, le=60)
    SCANNER_JOB_TIMEOUT_SECONDS: int = Field(default=300, ge=15, le=1800)
    SCANNER_HISTORY_RETENTION_DAYS: int = Field(default=30, ge=2, le=365)
    SCANNER_THNDR_MIN_INTERVAL_SECONDS: int = Field(default=300, ge=60, le=86400)
    ALERT_COOLDOWN_SECONDS: int = Field(default=21600, ge=0, le=604800)
    TELEGRAM_ENABLED: Literal[False] = False

    @field_validator("SCANNER_INTERVAL_SECONDS", mode="before")
    @classmethod
    def parse_interval(cls, value):
        return int(value) if isinstance(value, str) else value

    @field_validator("TELEGRAM_ENABLED", mode="before")
    @classmethod
    def parse_disabled(cls, value):
        return (
            False
            if isinstance(value, str) and value.lower() in {"false", "0", "no", "off"}
            else value
        )

    @model_validator(mode="after")
    def lease_has_room(self) -> Self:
        if self.SCANNER_HEARTBEAT_SECONDS * 3 > self.SCANNER_LEASE_SECONDS:
            raise ValueError("Lease must be at least three heartbeat intervals")
        return self


ENV = ScannerEnvironment()


class ScannerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    mode: Mode = "MARKET"
    interval_seconds: Literal[0, 60, 300, 900, 1800] = 0
    watchlist: list[Ticker] = Field(default_factory=list, max_length=150)
    manual: PortfolioSnapshot | None = None
    muted_categories: list[str] = Field(default_factory=list, max_length=20)
    minimum_severity: Literal["INFO", "OPPORTUNITY", "WARNING", "CRITICAL"] = "INFO"
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def selections(self) -> Self:
        if len(set(self.watchlist)) != len(self.watchlist):
            raise ValueError("Duplicate watchlist ticker")
        if self.mode == "MANUAL_PORTFOLIO" and self.manual is None:
            raise ValueError("Select an explicit manual portfolio")
        return self
