from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrderProposal(Base):
    __tablename__ = "order_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    active_intent: Mapped[str | None] = mapped_column(String(64), unique=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    created: Mapped[float] = mapped_column(Float, index=True)
    expires: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)


class TradingControl(Base):
    __tablename__ = "trading_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings: Mapped[dict] = mapped_column(JSON)
