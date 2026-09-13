import datetime
import time
from typing import List, Dict, Any, Optional
from app.services.data_provider.base import BaseHistoricalProvider

# Mapping of EGX Ticker symbols to Investing.com Instrument IDs
# Dynamic fallback mapping for securities not supported or delisted on Yahoo Finance
INVESTING_INSTRUMENT_MAP: Dict[str, int] = {
    "KORA": 1244005,  # Korra for Energy and Investment Projects (Korra Energi)
    "EGAL": 40587,    # Egypt Aluminum (EGAL)
}

class InvestingHistoricalProvider(BaseHistoricalProvider):
    """
    Real Fallback Provider: Investing.com Financial Chart Gateway.
    Fetches genuine historical OHLCV daily bars for EGX equities that Yahoo Finance cannot serve.
    Strictly authentic real data - zero mocks, zero synthetic bars.
    """

    @property
    def provider_name(self) -> str:
        return "Investing Historical"

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        instrument_id = INVESTING_INSTRUMENT_MAP.get(clean_ticker)

        if not instrument_id:
            # Not in mapped instruments and no dynamic resolution available
            return []

        # Request genuine historical daily chart data
        # Investing API strictly accepts pointscount in: [60, 70, 90, 110, 120, 140, 160]
        allowed_points = [60, 70, 90, 110, 120, 140, 160]
        points = 160
        for pt in allowed_points:
            if pt >= limit:
                points = pt
                break
        url = f"https://api.investing.com/api/financialdata/{instrument_id}/historical/chart/?interval=P1D&pointscount={points}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com"
        }

        # Use curl_cffi to bypass Cloudflare Turnstile bot detection
        from curl_cffi import requests

        for attempt in range(3):
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
                    if len(item) < 6:
                        continue
                    ts_ms = item[0]
                    session_dt = datetime.datetime.fromtimestamp(ts_ms / 1000, datetime.timezone.utc)
                    session_date = session_dt.strftime("%Y-%m-%d")

                    bars.append({
                        "ticker": clean_ticker,
                        "session_date": session_date,
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "actual_provider": self.provider_name,
                        "fetched_at": now_iso
                    })

                # Sort chronologically
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
        for b in bars:
            if b["session_date"] == session_date:
                return b
        return None
