import os
import datetime
from typing import List, Dict, Any, Optional
from app.services.data_provider.base import BaseHistoricalProvider

class EGIDProvider(BaseHistoricalProvider):
    """
    EGID (Egyptian Group for Information Dissemination) Gateway.
    Only active if genuinely configured and authenticated via EGID credentials.
    Zero fake data: returns None or [] if unauthenticated or unavailable.
    """
    @property
    def provider_name(self) -> str:
        return "EGID"

    @property
    def is_authenticated(self) -> bool:
        return bool(os.environ.get("EGID_API_KEY") and os.environ.get("EGID_CLIENT_SECRET"))

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        if not self.is_authenticated:
            return []
        return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        if not self.is_authenticated:
            return None
        return None

# Backwards compatibility alias
EGXDirectProvider = EGIDProvider