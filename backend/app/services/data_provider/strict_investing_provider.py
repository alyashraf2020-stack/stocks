from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

from app.services.data_provider.investing_provider import InvestingHistoricalProvider
from app.services.data_provider.investing_legacy_provider import InvestingLegacySearchProvider


class _InvestingTableParser(HTMLParser):
    """Extract real HTML table rows only.

    The old regional parser flattened the whole page to text. A date shown in a
    filter/range such as "... - 15/09/2026" could therefore be followed by
    unrelated quote numbers and be mistaken for an EOD candle. Restricting
    extraction to one actual <tr> prevents that class of false match.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
            self._cell = None
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = " ".join(self._cell)
            text = " ".join(text.replace("\u200e", "").replace("\u200f", "").split())
            self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


class _StrictInvestingMixin:
    REGIONAL_HOSTS = (
        "ca.investing.com",
        "au.investing.com",
        "www.investing.com",
        "uk.investing.com",
        "sa.investing.com",
        "ng.investing.com",
    )

    KNOWN_PAGE_URLS = {
        "KORA": "https://www.investing.com/equities/korra-energi",
        "EGAL": "https://www.investing.com/equities/egypt-aluminum",
    }

    def _resolve_metadata(self, ticker: str, english_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        meta = super()._resolve_metadata(clean_ticker, english_name)
        if meta is None:
            return None
        known_url = self.KNOWN_PAGE_URLS.get(clean_ticker)
        if known_url and not meta.get("url"):
            meta = dict(meta)
            meta["url"] = known_url
            self._resolved_url_cache[clean_ticker] = known_url
        return meta

    @staticmethod
    def _norm_cell(value: str) -> str:
        return " ".join(
            str(value or "")
            .replace("\u200e", "")
            .replace("\u200f", "")
            .replace("\u00a0", " ")
            .split()
        ).strip()

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

        parser = _InvestingTableParser()
        try:
            parser.feed(raw_html)
        except Exception:
            return None

        labels = {cls._norm_cell(label).lower() for label in cls._date_labels(session_date)}
        if not labels:
            return None

        for row in parser.rows:
            if len(row) < 6:
                continue

            first = cls._norm_cell(row[0]).lower()
            if first not in labels:
                continue

            close = cls._to_number(row[1])
            open_ = cls._to_number(row[2])
            high = cls._to_number(row[3])
            low = cls._to_number(row[4])
            volume = cls._to_number(row[5])
            if None in (close, open_, high, low, volume):
                continue

            close_f = float(close)
            open_f = float(open_)
            high_f = float(high)
            low_f = float(low)
            volume_f = float(volume)

            if min(open_f, high_f, low_f, close_f) <= 0 or volume_f < 0:
                continue
            if high_f < max(open_f, close_f, low_f):
                continue
            if low_f > min(open_f, close_f, high_f):
                continue

            import datetime

            return {
                "ticker": ticker.strip().upper(),
                "session_date": session_date,
                "open": open_f,
                "high": high_f,
                "low": low_f,
                "close": close_f,
                "volume": volume_f,
                "actual_provider": f"Investing Strict Regional Historical ({host})",
                "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

        return None


class StrictInvestingHistoricalProvider(_StrictInvestingMixin, InvestingHistoricalProvider):
    @property
    def provider_name(self) -> str:
        return "Investing Strict Historical"


class StrictInvestingLegacySearchProvider(_StrictInvestingMixin, InvestingLegacySearchProvider):
    @property
    def provider_name(self) -> str:
        return "Investing Strict Historical"
