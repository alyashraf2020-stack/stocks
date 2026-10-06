from sqlalchemy import Column, String, Text

from app.core.database import Base


class SecurityDataCorrection(Base):
    """One-time correction record retaining the superseded identity and candles."""

    __tablename__ = "egx_security_data_corrections"

    correction_id = Column(String(100), primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)
    applied_at = Column(String(50), nullable=False)
    archived_data = Column(Text, nullable=False)
