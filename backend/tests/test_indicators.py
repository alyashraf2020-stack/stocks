import pytest
from app.services.indicators import TechnicalIndicatorEngine
from app.services.data_provider.manager import default_provider_manager

def test_sma_periods_and_integrity():
    bars = [
        {"session_date": f"2026-01-{i+1:02d}", "open": 100.0, "high": 105.0, "low": 95.0, "close": float(100 + i), "volume": 1000.0}
        for i in range(60)
    ]
    enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
    assert len(enriched) == 60

    for i in range(19):
        assert enriched[i]["sma_20"] is None

    assert enriched[19]["sma_20"] == pytest.approx(109.5, 0.01)

    for i in range(49):
        assert enriched[i]["sma_50"] is None

    assert enriched[49]["sma_50"] == pytest.approx(124.5, 0.01)

def test_insufficient_bars_sma50_rule():
    short_bars = [
        {"session_date": f"2026-01-{i+1:02d}", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 500.0}
        for i in range(22)
    ]
    enriched = TechnicalIndicatorEngine.compute_all_indicators(short_bars)
    assert enriched[-1]["sma_20"] is not None
    assert enriched[-1]["sma_50"] is None

def test_macd_relationship():
    bars = [
        {"session_date": f"2026-01-{i+1:02d}", "open": 50.0, "high": 52.0, "low": 48.0, "close": float(50 + (i % 5)), "volume": 2000.0}
        for i in range(50)
    ]
    enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
    last = enriched[-1]
    if last["macd_line"] is not None and last["macd_signal"] is not None:
        expected_hist = round(last["macd_line"] - last["macd_signal"], 4)
        assert last["macd_hist"] == pytest.approx(expected_hist, 0.001)

def test_bollinger_bands_geometry():
    bars = [
        {"session_date": f"2026-01-{i+1:02d}", "open": 20.0, "high": 22.0, "low": 18.0, "close": float(20 + (i % 3)), "volume": 1000.0}
        for i in range(30)
    ]
    enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
    last = enriched[-1]
    assert last["bb_upper"] > last["bb_middle"]
    assert last["bb_middle"] > last["bb_lower"]
    expected_bw = (last["bb_upper"] - last["bb_lower"]) / last["bb_middle"]
    assert last["bb_bandwidth"] == pytest.approx(expected_bw, 0.001)

def test_atr_positive():
    bars = [
        {"session_date": f"2026-01-{i+1:02d}", "open": 30.0, "high": 35.0, "low": 28.0, "close": 32.0, "volume": 1500.0}
        for i in range(25)
    ]
    enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
    last = enriched[-1]
    assert last["atr_14"] is not None
    assert last["atr_14"] > 0

def test_real_stock_indicators():
    res = default_provider_manager.get_analytical_bars("COMI", limit=250)
    assert res["status"] in ("SUCCESS", "DATA_NOT_CURRENT")
    assert len(res["bars"]) >= 200
    enriched = TechnicalIndicatorEngine.compute_all_indicators(res["bars"])
    assert len(enriched) >= 200
    snapshot = TechnicalIndicatorEngine.get_latest_snapshot(enriched)
    assert snapshot["has_indicators"] is True
    assert snapshot["sma_20"] is not None
    assert snapshot["sma_50"] is not None
    assert 0 <= snapshot["rsi_14"] <= 100
    assert snapshot["atr_14"] > 0
    assert snapshot["bb_upper"] > snapshot["bb_lower"]