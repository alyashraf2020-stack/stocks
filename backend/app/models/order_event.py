from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("order_proposals.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    created: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON)
