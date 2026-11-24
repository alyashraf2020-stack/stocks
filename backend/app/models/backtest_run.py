from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queued: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    lease: Mapped[float | None] = mapped_column(Float)
    token: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(48))
    parameters: Mapped[dict] = mapped_column(JSON)


class SimulationDataset(Base):
    __tablename__ = "simulation_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    imported: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)
