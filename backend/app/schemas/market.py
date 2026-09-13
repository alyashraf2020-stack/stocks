from pydantic import BaseModel
from typing import Optional

class MarketStatusResponse(BaseModel):
    is_open_now: bool
    current_cairo_time: str
    expected_latest_completed_session: str
    total_listed_equities: int
    active_equities_count: int
    suspended_equities_count: int
    provenance_source: str
    provenance_updated_at: str