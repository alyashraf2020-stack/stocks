from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketImport(Base):
    __tablename__ = "market_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    dataset_id: Mapped[str | None] = mapped_column(String(36), index=True)
    ticker: Mapped[str | None] = mapped_column(String(20))
    session: Mapped[str | None] = mapped_column(String(10), index=True)
    created: Mapped[float] = mapped_column(Float, index=True)
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    report: Mapped[dict] = mapped_column(JSON)
