import datetime
import time
from typing import List, Dict, Any, Optional, Iterable
from urllib.parse import quote_plus

from app.services.data_provider.base import BaseHistoricalProvider

# Known mappings are kept only as fast paths. Every other EGX security is
# resolved automatically from Investing search by ticker + Security Master name.
INVESTING_INSTRUMENT_MAP: Dict[str, int] = {
    "KORA": 1244005,
    "EGAL": 40587,
}


class InvestingHistoricalProvider(BaseHistoricalProvider):
    """
    Real fallback provider for EGX equities using Investing historical charts.

    The provider is generic: it resolves unmapped stocks automatically instead
    of requiring a hand-written ticker map for every listed EGX security.
    No mocks, synthetic candles or forward-filled sessions are ever created.
    """

    _resolved_cache: Dict[str, int] = {}

    @property
    def provider_name(self) -> str:
        return "Investing Historical"

    @staticmethod
    def _headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com",
            "domain-id": "en",
            "DNT": "1",
        }

    @classmethod
    def _walk_dicts(cls, value: Any) -> Iterable[Dict[str, Any]]:
        """Yield dictionaries from any Investing search response shape."""
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_dicts(child)

    @staticmethod
    def _instrument_id(item: Dict[str, Any]) -> Optional[int]:
        raw_id = (
            item.get("pair_ID")
            or item.get("pairId")
            or item.get("pair_id")
            or item.get("instrumentId")
            or item.get("instrument_id")
            or item.get("financialDataId")
            or item.get("financial_data_id")
            or item.get("id")
        )
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())

    @classmethod
    def _score_candidate(
        cls,
        item: Dict[str, Any],
        ticker: str,
        english_name: Optional[str],
    ) -> int:
        symbol = str(
            item.get("symbol")
            or item.get("ticker")
            or item.get("short_name")
            or item.get("shortName")
            or ""
        ).strip().upper()

        country = cls._norm(
            item.get("country")
            or item.get("country_name")
            or item.get("countryName")
        )
        exchange = cls._norm(
            item.get("exchange")
            or item.get("exchange_name")
            or item.get("exchangeName")
        )
        item_type = cls._norm(item.get("type") or item.get("instrument_type") or item.get("instrumentType"))
        name = cls._norm(
            item.get("name")
            or item.get("full_name")
            or item.get("fullName")
            or item.get("description")
            or item.get("pair_name")
            or item.get("pairName")
        )

        score = 0
        clean_ticker = ticker.strip().upper()
        if symbol == clean_ticker:
            score += 120
        elif clean_ticker and clean_ticker.lower() in cls._norm(symbol):
            score += 55

        egypt_context = any(
            token in f"{country} {exchange}"
            for token in ("egypt", "egyptian", "cairo", "egx")
        )
        if egypt_context:
            score += 65

        if item_type and any(token in item_type for token in ("stock", "equity", "share")):
            score += 10

        if english_name:
            generic = {
                "the", "and", "for", "of", "company", "co", "sae", "s.a.e",
                "holding", "group", "services", "service", "egypt", "egyptian",
            }
            wanted_tokens = {
                token for token in cls._norm(english_name).split()
                if len(token) >= 4 and token not in generic
            }
            candidate_text = f"{name} {cls._norm(symbol)}"
            overlap = sum(1 for token in wanted_tokens if token in candidate_text)
            score += min(overlap * 18, 72)

        return score

    def _resolve_instrument_id(
        self,
        ticker: str,
        english_name: Optional[str] = None,
    ) -> Optional[int]:
        clean_ticker = ticker.strip().upper()

        if clean_ticker in INVESTING_INSTRUMENT_MAP:
            return INVESTING_INSTRUMENT_MAP[clean_ticker]
        if clean_ticker in self._resolved_cache:
            return self._resolved_cache[clean_ticker]

        queries: List[str] = [clean_ticker]
        if english_name:
            queries.extend([english_name, f"{english_name} Egypt"])

        best_id: Optional[int] = None
        best_score = -1

        try:
            from curl_cffi import requests

            session = requests.Session(impersonate="chrome124")

            for query in queries:
                search_url = f"https://api.investing.com/api/search/v2/search?q={quote_plus(query)}"
                try:
                    response = session.get(search_url, headers=self._headers(), timeout=15)
                    if response.status_code != 200:
                        continue
                    payload = response.json()
                except Exception:
                    continue

                for item in self._walk_dicts(payload):
                    instrument_id = self._instrument_id(item)
                    if instrument_id is None:
                        continue
                    score = self._score_candidate(item, clean_ticker, english_name)
                    if score > best_score:
                        best_score = score
                        best_id = instrument_id

                # An exact EGX ticker match is already strong enough; no reason
                # to keep making search requests.
                if best_score >= 170:
                    break

        except Exception:
            return None

        # Require strong evidence that the result belongs to the intended EGX
        # security. This avoids silently attaching another market's instrument.
        if best_id is not None and best_score >= 100:
            self._resolved_cache[clean_ticker] = best_id
            return best_id

        return None

    def fetch_historical_bars_for_security(
        self,
        ticker: str,
        english_name: Optional[str] = None,
        limit: int = 250,
    ) -> List[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        instrument_id = self._resolve_instrument_id(clean_ticker, english_name)
        if not instrument_id:
            return []
        return self._fetch_chart(clean_ticker, instrument_id, limit)

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        return self.fetch_historical_bars_for_security(ticker=ticker, english_name=None, limit=limit)

    def _fetch_chart(self, clean_ticker: str, instrument_id: int, limit: int) -> List[Dict[str, Any]]:
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

        from curl_cffi import requests

        for _attempt in range(3):
            try:
                session = requests.Session(impersonate="chrome124")
                response = session.get(url, headers=self._headers(), timeout=20)
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
                    if not isinstance(item, (list, tuple)) or len(item) < 6:
                        continue

                    try:
                        ts_ms = item[0]
                        session_dt = datetime.datetime.fromtimestamp(
                            ts_ms / 1000,
                            datetime.timezone.utc,
                        )
                        open_ = float(item[1])
                        high = float(item[2])
                        low = float(item[3])
                        close = float(item[4])
                        volume = float(item[5])
                    except (TypeError, ValueError, OSError, OverflowError):
                        continue

                    if min(open_, high, low, close) <= 0 or volume < 0:
                        continue
                    if high < max(open_, close, low) or low > min(open_, close, high):
                        continue

                    bars.append({
                        "ticker": clean_ticker,
                        "session_date": session_dt.strftime("%Y-%m-%d"),
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

        return []

    def fetch_session_bar_for_security(
        self,
        ticker: str,
        session_date: str,
        english_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        bars = self.fetch_historical_bars_for_security(
            ticker=ticker,
            english_name=english_name,
            limit=60,
        )
        for bar in bars:
            if bar["session_date"] == session_date:
                return bar
        return None

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        return self.fetch_session_bar_for_security(ticker, session_date, english_name=None)
