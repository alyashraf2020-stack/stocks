from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseHistoricalProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        """
        Fetches authentic historical daily bars for the given EGX equity ticker.
        Must return raw bars containing date, open, high, low, close, volume.
        Must NEVER return mock or synthetic data.
        Returns empty list if data is unavailable.
        """
        pass

    @abstractmethod
    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        """
        Attempts to fetch a single completed EGX session bar for the specified date.
        Used by the fallback pipeline to recover missing latest sessions.
        Returns None if not available from this real provider.
        """
        pass