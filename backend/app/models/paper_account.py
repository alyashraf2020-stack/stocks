from sqlalchemy import JSON, Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    created: Mapped[float] = mapped_column(Float)
    start_capital: Mapped[str] = mapped_column(String(28))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    automated: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_cursor: Mapped[str | None] = mapped_column(String(10))
    failure: Mapped[str | None] = mapped_column(String(48))
    strategy: Mapped[str] = mapped_column(String(16))
    datasets: Mapped[list] = mapped_column(JSON)
    execution: Mapped[dict] = mapped_column(JSON)
    book: Mapped[dict] = mapped_column(JSON)
    initial_request: Mapped[dict] = mapped_column(JSON)
