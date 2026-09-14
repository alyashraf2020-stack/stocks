import datetime
import html as html_lib
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from app.services.data_provider.base import BaseHistoricalProvider


class _TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = html_lib.unescape(" ".join(self._cell))
            text = re.sub(r"\s+", " ", text).strip()
            self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


class DirectFNCompletedSessionProvider(BaseHistoricalProvider):
    """Latest completed EGX-session fallback from DirectFN's public table.

    This provider is deliberately session-scoped. It never invents historical
    dates and only returns a bar when DirectFN's page explicitly shows the same
    market date requested by the caller.

    Some DirectFN rows expose Open as 0.00. In that case we do *not* fabricate
    an open. We only fill the Open from Mubasher when Mubasher's High/Low match
    the DirectFN row for the same market session; otherwise the provider returns
    None and the manager continues to the next source/manual recovery path.
    """

    TRADING_URL = "https://directfn.com.eg/tradingData.aspx"
    MUBASHER_URL = "https://english.mubasher.info/markets/EGX/stocks/{ticker}"

    @property
    def provider_name(self) -> str:
        return "DirectFN EGX"

    @staticmethod
    def _headers() -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @classmethod
    def _get_html(cls, url: str) -> Optional[str]:
        try:
            from curl_cffi import requests

            session = requests.Session(impersonate="chrome124")
            response = session.get(url, headers=cls._headers(), timeout=20)
            if response.status_code == 200 and response.text:
                return response.text
        except Exception:
            pass

        try:
            from urllib.request import Request, urlopen

            request = Request(url, headers=cls._headers())
            with urlopen(request, timeout=20) as response:  # nosec B310 - fixed HTTPS hosts
                raw = response.read()
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None

    @staticmethod
    def _number(value: str) -> Optional[float]:
        text = str(value or "").strip().replace(",", "")
        text = text.replace("−", "-")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _plain_text(raw_html: str) -> str:
        cleaned = re.sub(
            r"<(script|style)\b[^>]*>.*?</\1>",
            " ",
            raw_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        plain = html_lib.unescape(re.sub(r"<[^>]+>", " ", cleaned))
        return re.sub(r"\s+", " ", plain).strip()

    @classmethod
    def _extract_market_date(cls, raw_html: str) -> Optional[datetime.date]:
        # The page header contains values such as "13 Sep 2026".
        plain = cls._plain_text(raw_html)
        match = re.search(
            r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b",
            plain,
            re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return datetime.datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y"
            ).date()
        except ValueError:
            return None

    @classmethod
    def _extract_directfn_row(cls, raw_html: str, ticker: str) -> Optional[Dict[str, float]]:
        parser = _TableRowParser()
        try:
            parser.feed(raw_html)
        except Exception:
            return None

        clean_ticker = ticker.strip().upper()
        for row in parser.rows:
            # Expected columns:
            # Company Name | Symbol | Open | Last | High | Low | Change |
            # Change % | Volume | Turnover
            if len(row) < 10 or row[1].strip().upper() != clean_ticker:
                continue

            open_ = cls._number(row[2])
            close = cls._number(row[3])
            high = cls._number(row[4])
            low = cls._number(row[5])
            volume = cls._number(row[8])
            if None in (open_, close, high, low, volume):
                return None

            return {
                "open": float(open_),
                "close": float(close),
                "high": float(high),
                "low": float(low),
                "volume": float(volume),
            }
        return None

    @classmethod
    def _extract_mubasher_open_high_low(cls, raw_html: str) -> Optional[Dict[str, float]]:
        plain = cls._plain_text(raw_html)
        pattern = (
            r"\bOpen\s+([\d,.]+).*?"
            r"\bPrevious\s+Close\s+[\d,.]+.*?"
            r"\bHigh\s+([\d,.]+).*?"
            r"\bLow\s+([\d,.]+).*?"
            r"\bStock\s+Statistics\b.*?\bVolume\s+([\d,.]+)"
        )
        match = re.search(pattern, plain, re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        open_ = cls._number(match.group(1))
        high = cls._number(match.group(2))
        low = cls._number(match.group(3))
        volume = cls._number(match.group(4))
        if None in (open_, high, low, volume):
            return None
        return {
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "volume": float(volume),
        }

    @staticmethod
    def _prices_match(a: float, b: float) -> bool:
        tolerance = max(0.02, max(abs(a), abs(b)) * 0.0025)
        return abs(a - b) <= tolerance

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        # This source is intentionally only used to recover the latest completed
        # session; longer history continues to come from Yahoo/Investing/Stooq.
        return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        try:
            requested_date = datetime.date.fromisoformat(session_date)
        except ValueError:
            return None

        direct_html = self._get_html(self.TRADING_URL)
        if not direct_html:
            return None

        market_date = self._extract_market_date(direct_html)
        if market_date != requested_date:
            return None

        row = self._extract_directfn_row(direct_html, ticker)
        if not row:
            return None

        close = row["close"]
        high = row["high"]
        low = row["low"]
        volume = row["volume"]
        open_ = row["open"]

        if close <= 0 or high <= 0 or low <= 0 or volume < 0:
            return None
        if high < max(close, low) or low > min(close, high):
            return None

        provider = "DirectFN EGX"
        if open_ <= 0:
            mubasher_html = self._get_html(self.MUBASHER_URL.format(ticker=ticker.strip().upper()))
            if not mubasher_html:
                return None
            mubasher = self._extract_mubasher_open_high_low(mubasher_html)
            if not mubasher:
                return None

            # Date on the Mubasher quote page is not explicit enough for strict
            # session attribution, so it is only allowed to fill Open when its
            # High/Low corroborate DirectFN's exact dated row.
            if not self._prices_match(mubasher["high"], high):
                return None
            if not self._prices_match(mubasher["low"], low):
                return None
            open_ = mubasher["open"]
            provider = "DirectFN EGX + Mubasher verified open"

        if open_ <= 0 or not (low <= open_ <= high):
            return None

        return {
            "ticker": ticker.strip().upper(),
            "session_date": session_date,
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
            "actual_provider": provider,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
