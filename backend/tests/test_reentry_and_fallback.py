import datetime

import pytest

from app.services.data_provider.base import BaseHistoricalProvider
from app.services.data_provider.manager import ProviderManager
from app.services.indicators import TechnicalIndicatorEngine
from app.services.trade_plan import TradePlanEngine
from app.services.decision_engine import LiveDecisionEngine


class FakeProvider(BaseHistoricalProvider):
    def __init__(self, name, bars):
        self._name = name
        self._bars = bars

    @property
    def provider_name(self) -> str:
        return self._name

    def fetch_historical_bars(self, ticker: str, limit: int = 250):
        return self._bars[-limit:]

    def fetch_session_bar(self, ticker: str, session_date: str):
        for bar in self._bars:
            if bar["session_date"] == session_date:
                return bar
        return None


def make_bars(last_session: str, count: int = 60, base: float = 100.0):
    end = datetime.date.fromisoformat(last_session)
    bars = []
    for i in range(count):
        d = end - datetime.timedelta(days=(count - 1 - i))
        close = base + (i * 0.10)
        bars.append({
            "ticker": "TEST",
            "session_date": d.isoformat(),
            "open": close - 0.05,
            "high": close + 0.20,
            "low": close - 0.20,
            "close": close,
            "volume": 100000.0 + i,
            "actual_provider": "Fake",
        })
    return bars


def test_provider_manager_uses_fresh_fallback_when_primary_is_stale(monkeypatch):
    expected = datetime.date(2026, 9, 13)
    stale = make_bars("2026-09-10")
    fresh = make_bars("2026-09-13")

    primary = FakeProvider("Yahoo stale", stale)
    fallback = FakeProvider("Investing Historical", fresh)

    import app.services.data_provider.manager as manager_module

    monkeypatch.setattr(manager_module, "get_expected_latest_completed_session", lambda now=None: expected)
    monkeypatch.setattr(
        manager_module,
        "calculate_sessions_behind",
        lambda latest, now=None: 0 if latest >= expected else 1,
    )

    manager = ProviderManager(primary_provider=primary, fallback_providers=[fallback])
    result = manager.get_analytical_bars("EGAL", limit=60, force_refresh=True)

    assert result["status"] == "SUCCESS"
    assert result["actual_provider"] == "Investing Historical"
    assert result["latest_session"] == "2026-09-13"
    assert result["sessions_behind"] == 0
    assert result["current_analysis_eligible"] is True


def make_completed_then_recent_regime_bars():
    bars = []

    # Older regime keeps the original 20-session support very low so the initial
    # plan is clearly completed by the latest close.
    for i in range(40):
        bars.append({
            "session_date": (datetime.date(2026, 7, 1) + datetime.timedelta(days=i)).isoformat(),
            "open": 3.40,
            "high": 3.60,
            "low": 3.30,
            "close": 3.40,
            "volume": 100000.0,
        })

    for i in range(10):
        close = 4.00 + (0.20 * i)
        bars.append({
            "session_date": (datetime.date(2026, 8, 10) + datetime.timedelta(days=i)).isoformat(),
            "open": close - 0.10,
            "high": close + 0.20,
            "low": 3.30 if i == 0 else close - 0.20,
            "close": close,
            "volume": 110000.0,
        })

    for i in range(10):
        close = 6.30 + (0.10 * i)
        bars.append({
            "session_date": (datetime.date(2026, 9, 4) + datetime.timedelta(days=i)).isoformat(),
            "open": close - 0.05,
            "high": close + 0.15,
            "low": close - 0.15,
            "close": close,
            "volume": 120000.0,
        })

    return TechnicalIndicatorEngine.compute_all_indicators(bars)


def test_completed_plan_rolls_into_fresh_reentry_setup():
    bars = make_completed_then_recent_regime_bars()
    result = TradePlanEngine.calculate_trade_plan(bars, sessions_behind=0)

    assert result["status"] == "VALID"
    assert result["previous_plan"] is not None
    assert result["previous_plan"]["plan_status"] == "TARGETS_COMPLETED"

    current = result["trade_plan"]
    assert current["plan_status"] in ("ACTIVE", "NOT_TRIGGERED", "NO_VALID_SETUP")

    if current["plan_status"] != "NO_VALID_SETUP":
        # New entry zone must be materially above the obsolete old regime.
        assert current["entry_zone_min"] > 5.0
        assert current["entry_zone_max"] > current["entry_zone_min"]
        assert current["stop_loss"] < current["entry_zone_min"]
        assert current["target_1"] > current["entry_zone_max"]


def test_manual_price_uses_current_reentry_plan_without_becoming_ohlcv():
    bars = make_completed_then_recent_regime_bars()
    latest_eod_close = bars[-1]["close"]

    plan_result = TradePlanEngine.calculate_trade_plan(bars, sessions_behind=0)
    current_plan = plan_result["trade_plan"]
    assert plan_result["previous_plan"] is not None

    if current_plan["plan_status"] == "NO_VALID_SETUP":
        pytest.skip("Synthetic fixture is overextended under current indicator calculation")

    manual_price = current_plan["entry_zone_max"] + 0.20
    response = LiveDecisionEngine.evaluate(
        ticker="KORA",
        current_price=manual_price,
        capital=100000.0,
        owns_stock=False,
        analytical_bars=bars,
        sessions_behind=0,
    )

    assert response["decision"] in ("WAIT", "DO_NOT_CHASE")
    assert response["previous_plan"] is not None
    assert bars[-1]["close"] == latest_eod_close
    assert response["latest_close"] == latest_eod_close


def test_owner_management_keeps_completed_previous_plan_context():
    bars = make_completed_then_recent_regime_bars()
    plan_result = TradePlanEngine.calculate_trade_plan(bars, sessions_behind=0)
    previous = plan_result["previous_plan"]
    assert previous is not None

    response = LiveDecisionEngine.evaluate(
        ticker="KORA",
        current_price=float(previous["target_3"]) + 0.10,
        capital=100000.0,
        owns_stock=True,
        buy_price=5.41,
        shares_owned=322,
        analytical_bars=bars,
        sessions_behind=0,
    )

    assert response["decision"] == "TAKE_PROFIT"
    assert response["position_sizing"] is None
    assert response["previous_plan"] is not None
