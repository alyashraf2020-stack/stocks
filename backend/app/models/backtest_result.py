from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
