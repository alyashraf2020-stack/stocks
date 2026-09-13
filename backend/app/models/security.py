from sqlalchemy import Column, String, Text
from app.core.database import Base

class EGXSecurity(Base):
    __tablename__ = "egx_securities"

    ticker = Column(String(20), primary_key=True, index=True)
    arabic_name = Column(String(255), nullable=False, index=True)
    english_name = Column(String(255), nullable=False, index=True)
    isin = Column(String(20), nullable=True, index=True)
    sector = Column(String(100), nullable=False, index=True)
    listing_status = Column(String(20), default="ACTIVE")
    indices = Column(Text, default="[]")  # JSON string of index memberships
    source = Column(String(100), default="EGX Official Listed Equities Directory")
    source_updated_at = Column(String(50), nullable=False)

    def to_dict(self):
        import json
        return {
            "ticker": self.ticker,
            "arabic_name": self.arabic_name,
            "english_name": self.english_name,
            "isin": self.isin,
            "sector": self.sector,
            "listing_status": self.listing_status,
            "indices": json.loads(self.indices) if self.indices else [],
            "source": self.source,
            "source_updated_at": self.source_updated_at
        }
