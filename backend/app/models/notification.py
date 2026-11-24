from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    __tablename__ = "scanner_notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(12))
    created: Mapped[float] = mapped_column(Float, index=True)
    expires: Mapped[float] = mapped_column(Float)
    read_at: Mapped[float | None] = mapped_column(Float)
    acknowledged_at: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
