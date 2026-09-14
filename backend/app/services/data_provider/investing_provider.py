import datetime
import time
from typing import List, Dict, Any, Optional
from app.services.data_provider.base import BaseHistoricalProvider

# Known EGX mappings. Securities not listed here are resolved dynamically
# through Investing.com's search endpoint and cached at runtime.
INVESTING_INSTRUMENT_MAP: Dict[str, int] = {
    "KORA": 1244005,  # Korra for Energy and Investment Projects
    "EGAL": 40587,    # Egypt Aluminum
}


class InvestingHistoricalProvider(BaseHistoricalProvider):
    """
    Real fallback provider: Investing.com Financial Chart Gateway.
    Fetches genuine historical OHLCV daily bars for EGX equities.

    No mocks, no synthetic bars, no forward fill.
    Manual/live prices are never written into historical OHLCV.
    """

    _resolved_cache: Dict[str, int] = {}

    @property
    def provider_name(self) -> str:
        return "Investing Historical"

    def _resolve_instrument_id(self, ticker: str) -> Optional[int]:
        clean_ticker = ticker.strip().upper()

        if clean_ticker in INVESTING_INSTRUMENT_MAP:
            return INVESTING_INSTRUMENT_MAP[clean_ticker]
        if clean_ticker in self._resolved_cache:
            return self._resolved_cache[clean_ticker]

        # Dynamic resolver so unmapped EGX names such as TALM can still use the
        # Investing fallback when Yahoo is stale/unavailable.
        search_url = f"https://api.investing.com/api/search/v2/search?q={clean_ticker}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com",
            "domain-id": "en",
            "DNT": "1",
        }

        try:
            from curl_cffi import requests

            session = requests.Session(impersonate="chrome124")
            response = session.get(search_url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None

            payload = response.json()
            candidates = payload.get("quotes") or payload.get("data") or []
            if not isinstance(candidates, list):
                return None

            exact_matches = []
            egypt_matches = []

            for item in candidates:
                if not isinstance(item, dict):
                    continue

                symbol = str(
                    item.get("symbol")
                    or item.get("ticker")
                    or item.get("short_name")
                    or ""
                ).strip().upper()

                country = str(
                    item.get("country")
                    or item.get("country_name")
                    or item.get("countryName")
                    or ""
                ).strip().lower()

                exchange = str(
                    item.get("exchange")
                    or item.get("exchange_name")
                    or item.get("exchangeName")
                    or ""
                ).strip().lower()

                raw_id = (
                    item.get("pair_ID")
                    or item.get("pairId")
                    or item.get("pair_id")
                    or item.get("instrumentId")
                    or item.get("instrument_id")
                    or item.get("financialDataId")
                    or item.get("id")
                )

                try:
                    instrument_id = int(raw_id)
                except (TypeError, ValueError):
                    continue

                if symbol == clean_ticker:
                    exact_matches.append((instrument_id, country, exchange))

                if "egypt" in country or "egypt" in exchange or "cairo" in exchange:
                    egypt_matches.append((instrument_id, symbol))

            # Prefer exact ticker matches in Egypt/Cairo, then any exact ticker
            # match, then a unique Egypt/Cairo result.
            for instrument_id, country, exchange in exact_matches:
                if "egypt" in country or "egypt" in exchange or "cairo" in exchange:
                    self._resolved_cache[clean_ticker] = instrument_id
                    return instrument_id

            if exact_matches:
                instrument_id = exact_matches[0][0]
                self._resolved_cache[clean_ticker] = instrument_id
                return instrument_id

            if len(egypt_matches) == 1:
                instrument_id = egypt_matches[0][0]
                self._resolved_cache[clean_ticker] = instrument_id
                return instrument_id

        except Exception:
            return None

        return None

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        instrument_id = self._resolve_instrument_id(clean_ticker)

        if not instrument_id:
            return []

        # Investing chart gateway accepts these point counts.
        allowed_points = [60, 70, 90, 110, 120, 140, 160]
        points = 160
        for pt in allowed_points:
            if pt >= limit:
                points = pt
                break

        url = (
            f"https://api.investing.com/api/financialdata/{instrument_id}/historical/chart/"
            f"?interval=P1D&pointscount={points}"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com",
        }

        from curl_cffi import requests

        for _attempt in range(3):
            try:
                session = requests.Session(impersonate="chrome124")
                response = session.get(url, headers=headers, timeout=20)
                if response.status_code != 200:
                    time.sleep(1)
                    continue

                payload = response.json()
                raw_bars = payload.get("data", [])
                if not raw_bars:
                    return []

                bars: List[Dict[str, Any]] = []
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

                for item in raw_bars:
                    # Item format: [timestamp_ms, open, high, low, close, volume, ...]
                    if not isinstance(item, (list, tuple)) or len(item) < 6:
                        continue

                    ts_ms = item[0]
                    session_dt = datetime.datetime.fromtimestamp(
                        ts_ms / 1000,
                        datetime.timezone.utc,
                    )
                    session_date = session_dt.strftime("%Y-%m-%d")

                    try:
                        open_ = float(item[1])
                        high = float(item[2])
                        low = float(item[3])
                        close = float(item[4])
                        volume = float(item[5])
                    except (TypeError, ValueError):
                        continue

                    # Basic material OHLCV integrity check. Deeper validation is
                    # still performed later by the canonical validation pipeline.
                    if min(open_, high, low, close) <= 0:
                        continue
                    if high < max(open_, close, low):
                        continue
                    if low > min(open_, close, high):
                        continue
                    if volume < 0:
                        continue

                    bars.append({
                        "ticker": clean_ticker,
                        "session_date": session_date,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "actual_provider": self.provider_name,
                        "fetched_at": now_iso,
                    })

                bars.sort(key=lambda x: x["session_date"])

                if len(bars) > limit:
                    bars = bars[-limit:]

                return bars

            except Exception:
                time.sleep(1)
                continue

        return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        bars = self.fetch_historical_bars(ticker, limit=30)
        for bar in bars:
            if bar["session_date"] == session_date:
                return bar
        return None
