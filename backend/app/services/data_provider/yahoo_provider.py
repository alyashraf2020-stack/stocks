import datetime
from typing import List, Dict, Any, Optional
import yfinance as yf
from app.services.data_provider.base import BaseHistoricalProvider

class YahooEGXProvider(BaseHistoricalProvider):
    @property
    def provider_name(self) -> str:
        return "Yahoo Finance EGX"

    def fetch_historical_bars(self, ticker: str, limit: int = 250) -> List[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        yahoo_ticker = f"{clean_ticker}.CA"

        try:
            yt = yf.Ticker(yahoo_ticker)
            df = yt.history(period="1y", interval="1d", auto_adjust=False)
            
            if df.empty or len(df) == 0:
                return []

            bars: List[Dict[str, Any]] = []
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for ts, row in df.iterrows():
                session_date = ts.strftime("%Y-%m-%d")
                bars.append({
                    "ticker": clean_ticker,
                    "session_date": session_date,
                    "open": float(row.get("Open", 0.0)),
                    "high": float(row.get("High", 0.0)),
                    "low": float(row.get("Low", 0.0)),
                    "close": float(row.get("Close", 0.0)),
                    "volume": float(row.get("Volume", 0.0)),
                    "actual_provider": self.provider_name,
                    "fetched_at": now_iso
                })

            if len(bars) > limit:
                bars = bars[-limit:]

            return bars

        except Exception:
            return []

    def fetch_session_bar(self, ticker: str, session_date: str) -> Optional[Dict[str, Any]]:
        clean_ticker = ticker.strip().upper()
        yahoo_ticker = f"{clean_ticker}.CA"

        try:
            yt = yf.Ticker(yahoo_ticker)
            # Fetch a small window around the target session
            target_dt = datetime.date.fromisoformat(session_date)
            start_str = (target_dt - datetime.timedelta(days=2)).isoformat()
            end_str = (target_dt + datetime.timedelta(days=2)).isoformat()
            df = yt.history(start=start_str, end=end_str, interval="1d", auto_adjust=False)

            if df.empty:
                return None

            for ts, row in df.iterrows():
                if ts.strftime("%Y-%m-%d") == session_date:
                    return {
                        "ticker": clean_ticker,
                        "session_date": session_date,
                        "open": float(row.get("Open", 0.0)),
                        "high": float(row.get("High", 0.0)),
                        "low": float(row.get("Low", 0.0)),
                        "close": float(row.get("Close", 0.0)),
                        "volume": float(row.get("Volume", 0.0)),
                        "actual_provider": self.provider_name,
                        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
            return None
        except Exception:
            return None