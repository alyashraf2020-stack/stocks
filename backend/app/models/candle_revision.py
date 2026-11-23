"""Durable history of manual corrections and provider repairs."""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, JSON, String

from app.core.database import Base


class CandleRevision(Base):
    __tablename__ = "egx_candle_revisions"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), nullable=False)
    session_date = Column(String(10), nullable=False)
    recorded_at = Column(String(40), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())
    reason = Column(String(32), nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=False)
