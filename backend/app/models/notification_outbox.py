from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationOutbox(Base):
    __tablename__ = "scanner_notification_outbox"

    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(12), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[float] = mapped_column(Float)
    token: Mapped[str | None] = mapped_column(String(32))
    history: Mapped[list] = mapped_column(JSON, default=list)
