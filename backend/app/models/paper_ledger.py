from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperLedger(Base):
    __tablename__ = "paper_ledger"
    __table_args__ = (UniqueConstraint("account_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    created: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
