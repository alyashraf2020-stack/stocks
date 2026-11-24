from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    result_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_results.id"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario: Mapped[str] = mapped_column(String(48))
    data: Mapped[dict] = mapped_column(JSON)
