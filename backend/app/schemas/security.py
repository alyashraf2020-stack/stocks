from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class SecurityBase(BaseModel):
    ticker: str
    arabic_name: str
    english_name: str
    isin: Optional[str] = None
    sector: str
    listing_status: str = "ACTIVE"
    indices: List[str] = []
    source: str = "EGX Official Listed Equities Directory"
    source_updated_at: str

class SecurityResponse(SecurityBase):
    latest_close: Optional[float] = None
    latest_session_date: Optional[str] = None
    expected_session_date: Optional[str] = None
    sessions_behind: Optional[int] = None
    freshness: Optional[str] = None
    actual_provider: Optional[str] = None
    analysis_available: Optional[bool] = False
    analytical_bars_count: Optional[int] = None
    current_analysis_eligible: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

class SecurityListResponse(BaseModel):
    total: int
    provenance_source: str
    provenance_updated_at: str
    items: List[SecurityResponse]