import datetime
import json
from typing import List, Dict, Any, Optional, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.core.config import settings
from app.services.data_provider.base import BaseHistoricalProvider


class EGXAPIProvider(BaseHistoricalProvider):
    """Primary EGX market-data provider backed by EGXAPI.

    Uses authenticated REST market-data bars only. No synthetic candles,
    no forward fill, and no manual/live prices are written into OHLCV history.
    If the API is unavailable or the key is not configured, returns no data so
    the ProviderManager can continue to the existing real fallbacks.
    """

    BASE_URL = "https://api.egxapi.com/v2"

    @property
    def provider_name(self) -> str:
        return "EGXAPI"

    @property
    def is_configured(self) -> bool:
        return bool((settings.EGXAPI_KEY or "").strip())

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.EGXAPI_KEY.strip()}",
            "X-EGX-Env": (settings.EGXAPI_ENV or "paper").strip().lower(),
            "Accept": "application/json",
            "User-Agent": "egx-platform/1.0",
        }

    @staticmethod
    def _walk(value: Any) -> Iterable[Any]:
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from EGXAPIProvider._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from EGXAPIProvider._walk(child)

    @staticmethod
    def _first(item: Dict[str, Any], *keys: str) -> Any:
        lower = {str(k).lower(): v for k, v in item.items()}
        for key in keys:
            if key.lower() in lower:
                return lower[key.lower()]
        return None

    @classmethod
    def _date_from_value(cls, value: Any) -> Optional[str]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000.0
            try:
                return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date().isoformat()
            except (OSError, OverflowError, ValueError):
                return None

        text = str(value).strip()
        if not text:
            return None

        # Fast path for YYYY-MM-DD and ISO timestamps.
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]

        # Numeric timestamps sometimes arrive as strings.
        try:
            return cls._date_from_value(float(text))
        except ValueError:
            return None

    @classmethod
    def _normalize_bar(cls, item: Dict[str, Any], ticker: str) -> Optional[Dict[str, Any]]:
        session_date = cls._date_from_value(
            cls._first(item, "session_date", "date", "datetime", "timestamp", "time", "ts", "t", "start")
        )
        if not session_date:
            return None

        try:
            open_ = float(cls._first(item, "open", "o"))
            high = float(cls._first(item, "high", "h"))
            low = float(cls._first(item, "low", "l"))
            close = float(cls._first(item, "close", "c", "last"))
            volume_raw = cls._first(item, "volume", "v", "vol")
            volume = float(volume_raw if volume_raw is not None else 0)
        except (TypeError, ValueError):
            return None

        if min(open_, high, low, close) <= 0 or volume < 0:
            return None
        if high < max(open_, close, low) or low > min(open_, close, high):
            return None

        return {
            "ticker": ticker,
            "session_date": session_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "actual_provider": "EGXAPI",
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    @classmethod
    def _extract_bars(cls, payload: Any, ticker: str) -> List[Dict[str, Any]]:
        bars_by_date: Dict[str, Dict[str, Any]] = {}

        for node in cls._walk(payload):
            if not isinstance(node, dict):
                continue
            bar = cls._normalize_bar(node, ticker)
            if bar:
                bars_by_date[bar["session_date"]] = bar

        return [bars_by_date[d] for d in sorted(bars_by_date)]

    def _get_json(self, path: str, params: Dict[str, Any]) -> Optional[Any]:
        if not self.is_configured:
            return None

        url = f"{self.BASE_URL}{path}?{urlencode(params)}"
        request = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        if not self.is_configured:
            return []

        # Public EGXAPI docs show /v2/market-data/bars?symbol=...
        # Try common daily-bar parameter names, then the documented minimal form.
        attempts = [
            {"symbol": clean_ticker, "interval": "1d", "limit": limit},
            {"symbol": clean_ticker, "timeframe": "1d", "limit": limit},
            {"symbol": clean_ticker, "limit": limit},
            {"symbol": clean_ticker},
        ]

        for params in attempts:
            payload = self._get_json("/market-data/bars", params)
            if payload is None:
                continue
            bars = self._extract_bars(payload, clean_ticker)
            if bars:
                return bars[-limit:]

        return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        bars = self.fetch_historical_bars(ticker, limit=90)
        for bar in bars:
            if bar["session_date"] == session_date:
                return bar
        return None
