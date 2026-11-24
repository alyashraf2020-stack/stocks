from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TradingSignal(Base):
    __tablename__ = "scanner_signals"

    scope: Mapped[str] = mapped_column(String(40), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    updated: Mapped[float] = mapped_column(Float, index=True)
    data: Mapped[dict] = mapped_column(JSON)
