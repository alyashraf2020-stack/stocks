from typing import Dict, Any, List
import math
from datetime import date
from app.services.egx_calendar import is_egx_trading_day

class CandleValidator:
    @staticmethod
    def validate_open(raw_open: float, high: float, low: float) -> str:
        """
        Validates Open independently:
        - INVALID_OPEN: Non-positive, NaN, or None
        - OPEN_REFERENCE_ARTIFACT: Significantly outside session bounds (< 95% low or > 105% high)
        - OPEN_UNVERIFIED: Slightly outside [low, high] but within 5%
        - RAW_OPEN: Perfectly within [low, high]
        """
        if raw_open is None or not math.isfinite(raw_open) or raw_open <= 0:
            return "INVALID_OPEN"
        
        if high is None or low is None:
            return "OPEN_UNVERIFIED"
        if low <= raw_open <= high:
            return "RAW_OPEN"

        if raw_open < low * 0.95 or raw_open > high * 1.05:
            return "OPEN_REFERENCE_ARTIFACT"

        return "OPEN_UNVERIFIED"

    @staticmethod
    def validate_hlcv(high: float, low: float, close: float, volume: float) -> str:
        """
        Validates High, Low, Close, Volume:
        - High >= Low
        - High >= Close
        - Low <= Close
        - High > 0
        - Low > 0
        - Close > 0
        - Volume >= 0
        Returns VALID or INVALID.
        """
        if any(v is None or not math.isfinite(v) for v in (high, low, close, volume)):
            return "INVALID"

        if high <= 0 or low <= 0 or close <= 0 or volume < 0:
            return "INVALID"

        if high < low:
            return "INVALID"

        if high < close:
            return "INVALID"

        if low > close:
            return "INVALID"

        return "VALID"

    @classmethod
    def validate_bar(cls, bar: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates a single historical bar in-place/returns validated dict.
        Preserves original values without fabrication.
        """
        def numeric(field):
            value = bar.get(field)
            if isinstance(value, bool):
                return None
            try:
                return float(value)
            except (TypeError, ValueError, OverflowError):
                return None

        high, low, close, volume, raw_open = (numeric(key) for key in ("high", "low", "close", "volume", "open"))

        hlcv_status = cls.validate_hlcv(high, low, close, volume)
        open_status = cls.validate_open(raw_open, high, low)

        # Overall validation status
        if hlcv_status == "INVALID":
            validation_status = "INVALID"
        elif open_status != "RAW_OPEN":
            validation_status = open_status
        else:
            validation_status = "VALID"

        validated_bar = dict(bar)
        validated_bar["hlcv_status"] = hlcv_status
        validated_bar["open_status"] = open_status
        validated_bar["validation_status"] = validation_status
        return validated_bar

    @classmethod
    def validate_bars(cls, raw_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [cls.validate_bar(b) for b in raw_bars]

    @classmethod
    def extract_analytical_bars(cls, validated_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters out any bar where hlcv_status is INVALID.
        Never forward-fills, interpolates, or creates synthetic candles.
        """
        return [b for b in validated_bars if b.get("hlcv_status") == "VALID"]


def completed_analytical_bars(raw_bars, expected, ticker):
    """Validate EOD identity and chronology before caching or selecting a latest row."""
    by_date = {}
    conflicts = set()
    for raw in raw_bars:
        if not isinstance(raw, dict) or raw.get("ticker") != ticker:
            continue
        if raw.get("exchange", "EGX") != "EGX" or raw.get("currency", "EGP") != "EGP":
            continue
        if raw.get("validation_status") == "INVALID" or raw.get("hlcv_status") == "INVALID":
            continue
        try:
            session = date.fromisoformat(raw["session_date"])
        except (TypeError, KeyError, ValueError):
            continue
        if raw["session_date"] != session.isoformat() or session > expected or not is_egx_trading_day(session):
            continue
        bar = CandleValidator.validate_bar(raw)
        if bar["hlcv_status"] != "VALID" or bar["open_status"] == "INVALID_OPEN":
            continue
        previous = by_date.setdefault(session, bar)
        if previous is not bar and any(previous[k] != bar[k] for k in ("open", "high", "low", "close", "volume")):
            conflicts.add(session)
    return [by_date[session] for session in sorted(by_date.keys() - conflicts)]
