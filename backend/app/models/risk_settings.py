from sqlalchemy import JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RiskSettings(Base):
    __tablename__ = "owner_risk_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
