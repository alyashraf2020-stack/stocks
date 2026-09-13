from sqlalchemy import Column, Integer, String, Float, Index
from app.core.database import Base

class EGXCandle(Base):
    __tablename__ = "egx_candles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    session_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    actual_provider = Column(String(100), nullable=False)
    validation_status = Column(String(30), default="VALID")

    __table_args__ = (
        Index("ix_ticker_date", "ticker", "session_date", unique=True),
    )

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "session_date": self.session_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "actual_provider": self.actual_provider,
            "validation_status": self.validation_status
        }
