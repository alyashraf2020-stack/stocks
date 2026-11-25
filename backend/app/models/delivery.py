from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeliverySetting(Base):
    __tablename__ = "delivery_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    pair_hash: Mapped[str | None] = mapped_column(String(64))
    pair_expires: Mapped[float | None] = mapped_column(Float)
    next_pair_check: Mapped[float | None] = mapped_column(Float)


class DeliveryTarget(Base):
    __tablename__ = "delivery_targets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[str] = mapped_column(String(12))
    label: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean)
    since: Mapped[float] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer)
    secret: Mapped[str] = mapped_column(Text)
    last_ok: Mapped[float | None] = mapped_column(Float)


class ChannelDelivery(Base):
    __tablename__ = "channel_deliveries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notification_id: Mapped[str] = mapped_column(String(64), index=True)
    series: Mapped[str] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(12), index=True)
    target_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    created: Mapped[float] = mapped_column(Float)
    due: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16))
    token: Mapped[str | None] = mapped_column(String(32))
    lease: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(48))
    history: Mapped[list] = mapped_column(JSON, default=list)
    test: Mapped[bool] = mapped_column(Boolean, default=False)


class ChannelThrottle(Base):
    __tablename__ = "channel_throttle"
    channel: Mapped[str] = mapped_column(String(12), primary_key=True)
    until: Mapped[float] = mapped_column(Float)


class WorkerPulse(Base):
    __tablename__ = "worker_pulses"
    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    seen: Mapped[float] = mapped_column(Float)
