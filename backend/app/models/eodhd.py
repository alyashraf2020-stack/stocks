"""EODHD analytical cache and account-wide reservation state."""

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EodhdConfig(Base):
    __tablename__ = "eodhd_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    retry: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusive: Mapped[bool] = mapped_column(Boolean, default=False)
    catalog: Mapped[dict] = mapped_column(JSON, default=dict)
    last_status: Mapped[str | None] = mapped_column(String(40))
    checked: Mapped[float | None] = mapped_column(Float)


class EodhdUsage(Base):
    __tablename__ = "eodhd_usage"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    projected: Mapped[int] = mapped_column(Integer, default=0)
    upstream: Mapped[int | None] = mapped_column(Integer)


class EodhdCandle(Base):
    __tablename__ = "eodhd_candles"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    session_date: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    isin: Mapped[str] = mapped_column(String(20), primary_key=True)
    fetched: Mapped[float] = mapped_column(Float)
    bar: Mapped[dict] = mapped_column(JSON)


class EodhdSync(Base):
    __tablename__ = "eodhd_sync"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    target: Mapped[str] = mapped_column(String(10))
    attempts: Mapped[int] = mapped_column(Integer)
    tried: Mapped[float] = mapped_column(Float)
    next_try: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40))
