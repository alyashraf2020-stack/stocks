from typing import List, Dict, Any, Optional
from app.services.data_provider.base import BaseHistoricalProvider

class StooqEGXProvider(BaseHistoricalProvider):
    """
    Fallback Provider 2: Stooq secondary gateway.
    Zero fake data: returns None or [] if unavailable.
    """
    @property
    def provider_name(self) -> str:
        return "Stooq EGX Gateway"

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        return None