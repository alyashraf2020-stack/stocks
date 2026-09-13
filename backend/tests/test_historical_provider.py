from app.services.data_provider.manager import default_provider_manager

def test_real_provider_data_available_for_core_stock():
    result = default_provider_manager.get_analytical_bars("COMI", limit=100)
    # Under Zero-Session-Lag, status is SUCCESS (if current) or DATA_NOT_CURRENT (if exchange session completed before provider synced)
    assert result["status"] in ("SUCCESS", "DATA_NOT_CURRENT")
    assert "Yahoo" in result["actual_provider"]
    assert result["analytical_bars_count"] >= 50
    assert result["invalid_hlcv_bars"] == 0
    assert result["first_session"] is not None
    assert result["latest_session"] is not None
    assert "actionable_new_trade" not in result

def test_data_unavailable_for_invalid_ticker():
    result = default_provider_manager.get_analytical_bars("INVALID_NONEXISTENT_EGX_XYZ")
    assert result["status"] == "DATA_UNAVAILABLE"
    assert result["actual_provider"] is None
    assert result["analytical_bars_count"] == 0
    assert result["bars"] == []
    assert "actionable_new_trade" not in result

def test_no_synthetic_or_mock_bars():
    result = default_provider_manager.get_raw_historical_bars("FAKE_STOCK_123")
    assert result["status"] == "DATA_UNAVAILABLE"
    assert len(result["bars"]) == 0
    assert "actionable_new_trade" not in result

def test_investing_fallback_for_kora():
    result = default_provider_manager.get_analytical_bars("KORA", limit=160, force_refresh=True)
    assert result["status"] == "SUCCESS"
    assert result["actual_provider"] == "Investing Historical"
    assert result["analytical_bars_count"] >= 50
    assert result["sessions_behind"] == 0
    assert result["current_analysis_eligible"] is True
    assert result["latest_session"] == result["expected_latest_session"]
    assert "actionable_new_trade" not in result

def test_core_stocks_provider_isolation():
    for ticker in ["COMI", "SWDY", "MASR", "EGAL", "FWRY", "ABUK", "TMGH"]:
        result = default_provider_manager.get_analytical_bars(ticker, limit=100)
        assert result["status"] == "SUCCESS"
        assert result["actual_provider"] == "Yahoo Finance EGX"
        assert result["analytical_bars_count"] >= 50
        assert result["sessions_behind"] == 0
        assert result["current_analysis_eligible"] is True
        assert "actionable_new_trade" not in result