from sqlalchemy import JSON, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketScan(Base):
    __tablename__ = "scanner_runs"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[float] = mapped_column(Float, index=True)
    summary: Mapped[dict] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)
