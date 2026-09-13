from app.services.validator import CandleValidator

def test_hlcv_valid():
    status = CandleValidator.validate_hlcv(high=150.0, low=140.0, close=145.0, volume=10000.0)
    assert status == "VALID"

def test_hlcv_invalid_high_lower_than_low():
    status = CandleValidator.validate_hlcv(high=130.0, low=140.0, close=135.0, volume=10000.0)
    assert status == "INVALID"

def test_hlcv_invalid_high_lower_than_close():
    status = CandleValidator.validate_hlcv(high=140.0, low=130.0, close=145.0, volume=10000.0)
    assert status == "INVALID"

def test_hlcv_invalid_low_higher_than_close():
    status = CandleValidator.validate_hlcv(high=150.0, low=140.0, close=135.0, volume=10000.0)
    assert status == "INVALID"

def test_hlcv_invalid_non_positive_prices():
    assert CandleValidator.validate_hlcv(high=0.0, low=0.0, close=0.0, volume=100.0) == "INVALID"
    assert CandleValidator.validate_hlcv(high=10.0, low=-1.0, close=5.0, volume=100.0) == "INVALID"

def test_hlcv_invalid_negative_volume():
    assert CandleValidator.validate_hlcv(high=10.0, low=5.0, close=8.0, volume=-50.0) == "INVALID"

def test_open_validation_statuses():
    # In range [10.0, 20.0]
    assert CandleValidator.validate_open(15.0, high=20.0, low=10.0) == "RAW_OPEN"
    # Slightly outside [9.5 to 10.0) or (20.0 to 21.0] -> OPEN_UNVERIFIED
    assert CandleValidator.validate_open(9.8, high=20.0, low=10.0) == "OPEN_UNVERIFIED"
    assert CandleValidator.validate_open(20.5, high=20.0, low=10.0) == "OPEN_UNVERIFIED"
    # Far outside (< 9.5 or > 21.0) -> OPEN_REFERENCE_ARTIFACT
    assert CandleValidator.validate_open(5.0, high=20.0, low=10.0) == "OPEN_REFERENCE_ARTIFACT"
    assert CandleValidator.validate_open(25.0, high=20.0, low=10.0) == "OPEN_REFERENCE_ARTIFACT"
    # Non-positive or None -> INVALID_OPEN
    assert CandleValidator.validate_open(0.0, high=20.0, low=10.0) == "INVALID_OPEN"
    assert CandleValidator.validate_open(-5.0, high=20.0, low=10.0) == "INVALID_OPEN"

def test_questionable_open_does_not_invalidate_valid_hlcv():
    bar = {
        "ticker": "COMI",
        "session_date": "2026-09-09",
        "open": 5.0,  # Reference artifact far below low
        "high": 140.0,
        "low": 135.0,
        "close": 138.0,
        "volume": 50000.0,
        "actual_provider": "Yahoo Finance EGX"
    }
    validated = CandleValidator.validate_bar(bar)
    assert validated["hlcv_status"] == "VALID"
    assert validated["open_status"] == "OPEN_REFERENCE_ARTIFACT"
    assert validated["validation_status"] == "OPEN_REFERENCE_ARTIFACT"

    # Must STILL be included in analytical bars because HLCV is valid
    analytical = CandleValidator.extract_analytical_bars([validated])
    assert len(analytical) == 1
    assert analytical[0]["close"] == 138.0

def test_invalid_hlcv_excluded_from_analytical_bars():
    invalid_bar = {
        "ticker": "COMI",
        "session_date": "2026-09-09",
        "open": 136.0,
        "high": 130.0,  # High lower than Low!
        "low": 135.0,
        "close": 132.0,
        "volume": 50000.0,
        "actual_provider": "Yahoo Finance EGX"
    }
    validated = CandleValidator.validate_bar(invalid_bar)
    assert validated["hlcv_status"] == "INVALID"
    analytical = CandleValidator.extract_analytical_bars([validated])
    assert len(analytical) == 0  # Materially invalid HLCV barred from analytical series