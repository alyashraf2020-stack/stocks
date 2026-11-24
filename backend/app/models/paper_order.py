from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    account_id: Mapped[str] = mapped_column(
        ForeignKey("paper_accounts.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)
