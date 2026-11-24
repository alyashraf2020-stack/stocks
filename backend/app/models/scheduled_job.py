from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScannerControl(Base):
    __tablename__ = "scanner_control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    last_broker_check: Mapped[float | None] = mapped_column(Float)


class ScheduledJob(Base):
    __tablename__ = "scanner_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window: Mapped[str] = mapped_column(String(100), unique=True)
    revision: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    session: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    queued: Mapped[float] = mapped_column(Float, index=True)
    due: Mapped[float] = mapped_column(Float)
    started: Mapped[float | None] = mapped_column(Float)
    finished: Mapped[float | None] = mapped_column(Float)
    lease_until: Mapped[float | None] = mapped_column(Float)
    token: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(String(40))


class ScannerHeartbeat(Base):
    __tablename__ = "scanner_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    seen: Mapped[float] = mapped_column(Float, index=True)
    job_id: Mapped[int | None] = mapped_column(Integer)


class ScannerAudit(Base):
    __tablename__ = "scanner_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[float] = mapped_column(Float, index=True)
    action: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[int | None] = mapped_column(Integer)
