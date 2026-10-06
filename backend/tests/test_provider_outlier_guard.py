from app.services.data_provider.manager import ProviderManager


def _bar(date: str, open_: float, high: float, low: float, close: float):
    return {
        "session_date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100000,
    }


def test_large_single_source_jump_is_flagged():
    bar = _bar("2026-09-14", 226.95, 237.98, 226.95, 235.50)
    assert ProviderManager._is_large_close_jump(371.05, bar) is True


def test_normal_session_move_is_not_flagged():
    bar = _bar("2026-09-14", 365.0, 370.0, 360.0, 365.49)
    assert ProviderManager._is_large_close_jump(371.05, bar) is False


def test_two_sources_can_corroborate_large_discontinuity():
    first = _bar("2026-09-14", 226.95, 237.98, 226.95, 235.50)
    second = _bar("2026-09-14", 227.20, 238.10, 226.80, 235.80)
    assert ProviderManager._bars_corroborate(first, second) is True


def test_mismatched_sources_do_not_corroborate():
    first = _bar("2026-09-14", 226.95, 237.98, 226.95, 235.50)
    second = _bar("2026-09-14", 360.0, 370.0, 355.0, 365.0)
    assert ProviderManager._bars_corroborate(first, second) is False
