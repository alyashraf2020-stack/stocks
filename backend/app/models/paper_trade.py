from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    __table_args__ = (UniqueConstraint("account_id", "order_id", "session"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(36))
    session: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict] = mapped_column(JSON)
