from typing import Dict, Any, List, Tuple
import math

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
        if raw_open is None or math.isnan(raw_open) or raw_open <= 0:
            return "INVALID_OPEN"
        
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
        if any(v is None or math.isnan(v) for v in (high, low, close, volume)):
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
        high = float(bar.get("high", 0.0))
        low = float(bar.get("low", 0.0))
        close = float(bar.get("close", 0.0))
        volume = float(bar.get("volume", 0.0))
        raw_open = float(bar.get("open", 0.0))

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