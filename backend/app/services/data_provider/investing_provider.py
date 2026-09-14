import datetime
import html as html_lib
import re
import time
from typing import List, Dict, Any, Optional, Iterable
from urllib.parse import quote_plus, urlparse

from app.services.data_provider.base import BaseHistoricalProvider

# Known mappings are kept only as fast paths. Every other EGX security is
# resolved automatically from Investing search by ticker + Security Master name.
INVESTING_INSTRUMENT_MAP: Dict[str, int] = {
    "KORA": 1244005,
    "EGAL": 40587,
}


class InvestingHistoricalProvider(BaseHistoricalProvider):
    """Public Investing fallback for EGX equities.

    The normal chart feed is preferred. If it is missing the latest completed
    EGX session, regional Investing historical pages are checked for an explicit
    row for that exact session date. A row is accepted only when full OHLCV is
    present and internally valid. Live/manual prices are never converted into
    EOD candles.
    """

    REGIONAL_HOSTS = (
        "au.investing.com",
        "www.investing.com",
        "ca.investing.com",
        "uk.investing.com",
        "sa.investing.com",
        "ng.investing.com",
    )

    _resolved_cache: Dict[str, int] = {}
    _resolved_url_cache: Dict[str, str] = {}

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
    def _candidate_url(item: Dict[str, Any]) -> Optional[str]:
        raw = (
            item.get("url")
            or item.get("link")
            or item.get("href")
            or item.get("url_name")
            or item.get("urlName")
        )
        if not raw:
            return None
        value = str(raw).strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("/"):
            return f"https://www.investing.com{value}"
        if "/" not in value:
            return f"https://www.investing.com/equities/{value}"
        return f"https://www.investing.com/{value.lstrip('/')}"

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())

    @classmethod
    def _score_candidate(cls, item: Dict[str, Any], ticker: str, english_name: Optional[str]) -> int:
        symbol = str(
            item.get("symbol")
            or item.get("ticker")
            or item.get("short_name")
            or item.get("shortName")
            or ""
        ).strip().upper()
        country = cls._norm(item.get("country") or item.get("country_name") or item.get("countryName"))
        exchange = cls._norm(item.get("exchange") or item.get("exchange_name") or item.get("exchangeName"))
        item_type = cls._norm(item.get("type") or item.get("instrument_type") or item.get("instrumentType"))
        name = cls._norm(
            item.get("name")
            or item.get("full_name")
            or item.get("fullName")
            or item.get("description")
            or item.get("pair_name")
            or item.get("pairName")
        )

        clean_ticker = ticker.strip().upper()
        score = 0
        if symbol == clean_ticker:
            score += 120
        elif clean_ticker and clean_ticker.lower() in cls._norm(symbol):
            score += 55

        context = f"{country} {exchange}"
        if any(token in context for token in ("egypt", "egyptian", "cairo", "egx")):
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
            score += min(sum(1 for token in wanted_tokens if token in candidate_text) * 18, 72)
        return score

    def _resolve_metadata(self, ticker: str, english_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        if clean_ticker in self._resolved_cache:
            return {
                "id": self._resolved_cache[clean_ticker],
                "url": self._resolved_url_cache.get(clean_ticker),
            }

        if clean_ticker in INVESTING_INSTRUMENT_MAP:
            self._resolved_cache[clean_ticker] = INVESTING_INSTRUMENT_MAP[clean_ticker]
            return {"id": INVESTING_INSTRUMENT_MAP[clean_ticker], "url": None}

        queries: List[str] = [clean_ticker]
        if english_name:
            queries.extend([english_name, f"{english_name} Egypt"])

        best: Optional[Dict[str, Any]] = None
        best_score = -1
        try:
            from curl_cffi import requests
            session = requests.Session(impersonate="chrome124")
            for query in queries:
                url = f"https://api.investing.com/api/search/v2/search?q={quote_plus(query)}"
                try:
                    response = session.get(url, headers=self._headers(), timeout=15)
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
                        best = {"id": instrument_id, "url": self._candidate_url(item)}
                if best_score >= 170:
                    break
        except Exception:
            return None

        if best is not None and best_score >= 100:
            self._resolved_cache[clean_ticker] = int(best["id"])
            if best.get("url"):
                self._resolved_url_cache[clean_ticker] = str(best["url"])
            return best
        return None

    def _resolve_instrument_id(self, ticker: str, english_name: Optional[str] = None) -> Optional[int]:
        meta = self._resolve_metadata(ticker, english_name)
        return int(meta["id"]) if meta else None

    def fetch_historical_bars_for_security(
        self, ticker: str, english_name: Optional[str] = None, limit: int = 250
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
        points = next((pt for pt in allowed_points if pt >= limit), 160)
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
                raw_bars = response.json().get("data", [])
                if not raw_bars:
                    return []

                bars: List[Dict[str, Any]] = []
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for item in raw_bars:
                    if not isinstance(item, (list, tuple)) or len(item) < 6:
                        continue
                    try:
                        session_dt = datetime.datetime.fromtimestamp(float(item[0]) / 1000, datetime.timezone.utc)
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
                return bars[-limit:] if len(bars) > limit else bars
            except Exception:
                time.sleep(1)
        return []

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip().replace(",", "").replace("\u00a0", " ")
        if not text or text in ("-", "—"):
            return None
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*([KMB])?", text, re.IGNORECASE)
        if not match:
            return None
        number = float(match.group(1))
        suffix = (match.group(2) or "").upper()
        if suffix == "K":
            number *= 1_000
        elif suffix == "M":
            number *= 1_000_000
        elif suffix == "B":
            number *= 1_000_000_000
        return number

    @classmethod
    def _regional_historical_urls(cls, base_url: str) -> List[str]:
        parsed = urlparse(base_url)
        path = parsed.path.rstrip("/")
        if not path:
            return []
        historical_path = path if path.endswith("-historical-data") else f"{path}-historical-data"
        return [f"https://{host}{historical_path}" for host in cls.REGIONAL_HOSTS]

    @staticmethod
    def _date_labels(session_date: str) -> List[str]:
        try:
            date_value = datetime.date.fromisoformat(session_date)
        except ValueError:
            return []
        return [
            date_value.strftime("%d/%m/%Y"),
            date_value.strftime("%m/%d/%Y"),
            date_value.strftime("%b %d, %Y"),
            date_value.strftime("%d %b %Y"),
            date_value.strftime("%b %d %Y"),
        ]

    @classmethod
    def _parse_historical_session_row(
        cls,
        raw_html: str,
        ticker: str,
        session_date: str,
        host: str = "regional.investing.com",
    ) -> Optional[Dict[str, Any]]:
        if not raw_html:
            return None

        cleaned = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        plain = html_lib.unescape(re.sub(r"<[^>]+>", " ", cleaned))
        plain = plain.replace("|", " ").replace("\u00a0", " ")
        plain = re.sub(r"\s+", " ", plain)

        number = r"([+-]?\d[\d,]*(?:\.\d+)?\s*[KMB]?)"
        for label in cls._date_labels(session_date):
            pattern = rf"{re.escape(label)}\s+{number}\s+{number}\s+{number}\s+{number}\s+{number}(?=\s|$)"
            match = re.search(pattern, plain, re.IGNORECASE)
            if not match:
                continue

            close = cls._to_number(match.group(1))
            open_ = cls._to_number(match.group(2))
            high = cls._to_number(match.group(3))
            low = cls._to_number(match.group(4))
            volume = cls._to_number(match.group(5))
            if None in (close, open_, high, low, volume):
                continue

            close_f = float(close)
            open_f = float(open_)
            high_f = float(high)
            low_f = float(low)
            volume_f = float(volume)
            if min(open_f, high_f, low_f, close_f) <= 0 or volume_f < 0:
                continue
            if high_f < max(open_f, close_f, low_f) or low_f > min(open_f, close_f, high_f):
                continue

            return {
                "ticker": ticker.strip().upper(),
                "session_date": session_date,
                "open": open_f,
                "high": high_f,
                "low": low_f,
                "close": close_f,
                "volume": volume_f,
                "actual_provider": f"Investing Regional Historical ({host})",
                "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        return None

    def _fetch_regional_historical_bar(
        self,
        ticker: str,
        session_date: str,
        english_name: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        meta = self._resolve_metadata(clean_ticker, english_name)
        if not meta or not meta.get("url"):
            return None

        urls = self._regional_historical_urls(str(meta["url"]))
        if not urls:
            return None

        try:
            from curl_cffi import requests
            session = requests.Session(impersonate="chrome124")
        except Exception:
            return None

        for url in urls:
            try:
                parsed = urlparse(url)
                headers = dict(self._headers())
                headers["Accept"] = "text/html,application/xhtml+xml"
                headers["Referer"] = f"https://{parsed.netloc}/"
                headers.pop("Origin", None)
                response = session.get(url, headers=headers, timeout=20)
                if response.status_code != 200:
                    continue
                bar = self._parse_historical_session_row(
                    response.text,
                    ticker=clean_ticker,
                    session_date=session_date,
                    host=parsed.netloc,
                )
                if bar is not None:
                    return bar
            except Exception:
                continue
        return None

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

        # The regional fallback must contain an explicit row for the requested
        # completed date. We deliberately do not relabel a live/current quote.
        return self._fetch_regional_historical_bar(ticker, session_date, english_name)

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        return self.fetch_session_bar_for_security(ticker, session_date, english_name=None)
