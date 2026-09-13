import math
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

class TechnicalIndicatorEngine:
    """
    Computes technical indicators deterministically on full historical analytical series.
    Indicators are computed on the entire history BEFORE any date slicing is performed.
    Supported indicators:
    - SMA20
    - SMA50
    - RSI14 (Wilder smoothing)
    - MACD (12, 26, 9) (MACD Line, Signal Line, Histogram)
    - Bollinger Bands (20, 2.0) (Upper, Middle, Lower, Bandwidth)
    - ATR14 (Wilder smoothing Average True Range)
    """

    @classmethod
    def compute_all_indicators(cls, analytical_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not analytical_bars or len(analytical_bars) == 0:
            return []

        df = pd.DataFrame(analytical_bars)
        # Ensure correct datatypes
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        n_bars = len(df)

        # 1. SMA 20
        df["sma_20"] = df["close"].rolling(window=20, min_periods=20).mean()

        # 2. SMA 50
        df["sma_50"] = df["close"].rolling(window=50, min_periods=50).mean()

        # 3. RSI 14 (Wilder's Smoothing)
        delta = df["close"].diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        
        # Wilder's exponential smoothing uses alpha = 1 / period
        avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        # Where avg_loss was 0, if avg_gain > 0 RSI = 100, else 50
        rsi = rsi.fillna(100.0).where(avg_loss == 0.0, rsi)
        df["rsi_14"] = rsi

        # 4. MACD (12, 26, 9)
        ema_12 = df["close"].ewm(span=12, min_periods=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, min_periods=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, min_periods=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        df["macd_line"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = macd_hist

        # 5. Bollinger Bands (20, 2.0)
        bb_middle = df["sma_20"]
        bb_std = df["close"].rolling(window=20, min_periods=20).std(ddof=0)
        df["bb_middle"] = bb_middle
        df["bb_upper"] = bb_middle + (2.0 * bb_std)
        df["bb_lower"] = bb_middle - (2.0 * bb_std)
        df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / bb_middle.replace(0.0, np.nan)

        # 6. ATR 14 (Average True Range with Wilder's Smoothing)
        prev_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr_14"] = true_range.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()

        # Convert back to clean list of dicts with Python native types (handling NaN -> None)
        enriched_bars: List[Dict[str, Any]] = []
        for i, row in df.iterrows():
            bar_dict = dict(analytical_bars[i])
            for col in [
                "sma_20", "sma_50", "rsi_14", "macd_line", "macd_signal",
                "macd_hist", "bb_middle", "bb_upper", "bb_lower", "bb_bandwidth", "atr_14"
            ]:
                val = row[col]
                bar_dict[col] = None if pd.isna(val) else round(float(val), 4)
            enriched_bars.append(bar_dict)

        return enriched_bars

    @classmethod
    def get_latest_snapshot(cls, enriched_bars: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extracts the most recent calculated technical indicators from the last bar.
        """
        if not enriched_bars:
            return {
                "has_indicators": False,
                "sma_20": None,
                "sma_50": None,
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "macd_hist": None,
                "bb_upper": None,
                "bb_middle": None,
                "bb_lower": None,
                "bb_bandwidth": None,
                "atr_14": None
            }

        last = enriched_bars[-1]
        has_indicators = (
            last.get("sma_20") is not None and
            last.get("sma_50") is not None and
            last.get("rsi_14") is not None
        )

        return {
            "has_indicators": has_indicators,
            "session_date": last.get("session_date"),
            "close": last.get("close"),
            "sma_20": last.get("sma_20"),
            "sma_50": last.get("sma_50"),
            "rsi_14": last.get("rsi_14"),
            "macd_line": last.get("macd_line"),
            "macd_signal": last.get("macd_signal"),
            "macd_hist": last.get("macd_hist"),
            "bb_upper": last.get("bb_upper"),
            "bb_middle": last.get("bb_middle"),
            "bb_lower": last.get("bb_lower"),
            "bb_bandwidth": last.get("bb_bandwidth"),
            "atr_14": last.get("atr_14")
        }