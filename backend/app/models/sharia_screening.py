from datetime import date

from sqlalchemy import JSON, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShariaScreening(Base):
    __tablename__ = "sharia_screening"

    isin: Mapped[str] = mapped_column(String(20), primary_key=True)
    reviewed_on: Mapped[date] = mapped_column(Date, primary_key=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
