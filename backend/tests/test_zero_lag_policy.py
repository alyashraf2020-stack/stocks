import datetime
import pytest
from app.services.egx_calendar import (
    is_egx_trading_day,
    get_expected_latest_completed_session,
    calculate_sessions_behind,
    get_freshness_label,
    CAIRO_TZ
)
from app.services.decision_engine import LiveDecisionEngine
from app.services.trade_plan import TradePlanEngine
from app.services.indicators import TechnicalIndicatorEngine
from app.services.data_provider.base import BaseHistoricalProvider
from app.services.data_provider.manager import ProviderManager

@pytest.fixture
def valid_50_bars():
    bars = []
    base_price = 100.0
    for i in range(55):
        c = base_price + (i * 0.2)
        bars.append({
            "session_date": f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}",
            "open": c - 0.5,
            "high": c + 1.0,
            "low": c - 1.0,
            "close": c,
            "volume": 50000.0,
            "hlcv_status": "VALID"
        })
    return TechnicalIndicatorEngine.compute_all_indicators(bars)

def test_sessions_behind_0_allows_current_analysis(valid_50_bars):
    # sessions_behind = 0 -> current analysis allowed
    plan = TradePlanEngine.calculate_trade_plan(valid_50_bars, sessions_behind=0)
    assert plan["status"] == "VALID"
    assert plan["actionable_new_trade"] is True

    # Price inside entry zone -> ENTER_NOW is permitted
    e_mid = (plan["trade_plan"]["entry_zone_min"] + plan["trade_plan"]["entry_zone_max"]) / 2.0
    decision = LiveDecisionEngine.evaluate("COMI", e_mid, 100000.0, owns_stock=False, analytical_bars=valid_50_bars, sessions_behind=0)
    assert decision["decision"] == "ENTER_NOW"
    assert decision["actionable_new_trade"] is True

def test_sessions_behind_1_blocks_current_entry(valid_50_bars):
    # sessions_behind = 1 -> current entry blocked
    plan = TradePlanEngine.calculate_trade_plan(valid_50_bars, sessions_behind=1)
    assert plan["status"] == "DATA_NOT_CURRENT"
    assert plan["actionable_new_trade"] is False
    assert plan["trade_plan"] is None

    # Live decision MUST return DATA_NOT_CURRENT and NEVER ENTER_NOW
    decision = LiveDecisionEngine.evaluate("COMI", 100.0, 100000.0, owns_stock=False, analytical_bars=valid_50_bars, sessions_behind=1)
    assert decision["decision"] == "DATA_NOT_CURRENT"
    assert decision["actionable_new_trade"] is False
    assert "بيانات آخر جلسة غير متاحة" in decision["reason_ar"]

def test_sessions_behind_2_blocks_current_entry(valid_50_bars):
    # sessions_behind = 2 -> current entry blocked
    plan = TradePlanEngine.calculate_trade_plan(valid_50_bars, sessions_behind=2)
    assert plan["status"] == "DATA_NOT_CURRENT"
    assert plan["actionable_new_trade"] is False

    decision = LiveDecisionEngine.evaluate("COMI", 100.0, 100000.0, owns_stock=False, analytical_bars=valid_50_bars, sessions_behind=2)
    assert decision["decision"] == "DATA_NOT_CURRENT"
    assert decision["actionable_new_trade"] is False

def test_weekend_not_incorrectly_counted_as_missing_session():
    # Friday 2026-09-11 and Saturday 2026-09-12
    # Latest completed was Thursday 2026-09-10
    # On Saturday 2026-09-12, expected completed is still Thursday 2026-09-10
    saturday_noon = datetime.datetime(2026, 9, 12, 12, 0, 0, tzinfo=CAIRO_TZ)
    expected = get_expected_latest_completed_session(saturday_noon)
    assert expected == datetime.date(2026, 9, 10)

    # Data from Thursday 2026-09-10 has sessions_behind == 0!
    behind = calculate_sessions_behind(datetime.date(2026, 9, 10), saturday_noon)
    assert behind == 0
    assert get_freshness_label(behind) == "CURRENT"

def test_egx_holiday_not_incorrectly_counted():
    # Coptic Christmas: 2026-01-07 (Wednesday) is holiday.
    # On Wednesday 2026-01-07, latest completed was Tuesday 2026-01-06.
    holiday_time = datetime.datetime(2026, 1, 7, 12, 0, 0, tzinfo=CAIRO_TZ)
    expected = get_expected_latest_completed_session(holiday_time)
    assert expected == datetime.date(2026, 1, 6)

    # If data is from 2026-01-06, sessions_behind is 0 (holiday was not counted as missed)
    behind = calculate_sessions_behind(datetime.date(2026, 1, 6), holiday_time)
    assert behind == 0

def test_during_active_session_current_unfinished_not_required():
    # Wednesday 2026-09-09 at 11:30 AM Cairo time (session in progress, closes at 14:30)
    during_session = datetime.datetime(2026, 9, 9, 11, 30, 0, tzinfo=CAIRO_TZ)
    expected = get_expected_latest_completed_session(during_session)
    # Must NOT require today's incomplete session; must require Tuesday 2026-09-08
    assert expected == datetime.date(2026, 9, 8)

    # Data from Tuesday 2026-09-08 is fully current (0 sessions behind)
    behind = calculate_sessions_behind(datetime.date(2026, 9, 8), during_session)
    assert behind == 0

def test_after_completed_session_latest_completed_required():
    # Wednesday 2026-09-09 at 15:00 Cairo time (session officially closed at 14:30)
    after_close = datetime.datetime(2026, 9, 9, 15, 0, 0, tzinfo=CAIRO_TZ)
    expected = get_expected_latest_completed_session(after_close)
    # Today's completed session 2026-09-09 IS NOW REQUIRED
    assert expected == datetime.date(2026, 9, 9)

    # Data from Tuesday 2026-09-08 is now 1 session behind
    behind = calculate_sessions_behind(datetime.date(2026, 9, 8), after_close)
    assert behind == 1
    assert get_freshness_label(behind) == "OUTDATED"

class MockPrimaryMissingLatest(BaseHistoricalProvider):
    @property
    def provider_name(self) -> str:
        return "Mock Primary (Missing Latest)"

    def fetch_historical_bars(self, ticker: str, limit: int = 250):
        # Returns 60 history bars ending at 2026-09-08 (missing latest expected session)
        bars = []
        for i in range(60, 0, -1):
            bars.append({
                "ticker": ticker,
                "session_date": f"2026-06-{i:02d}" if i <= 30 else f"2026-07-{(i-30):02d}",
                "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000.0
            })
        bars[-1]["session_date"] = "2026-09-08"
        return bars

    def fetch_session_bar(self, ticker: str, session_date: str):
        return None

class MockFallbackHasLatest(BaseHistoricalProvider):
    @property
    def provider_name(self) -> str:
        return "Mock Fallback (Has Latest)"

    def fetch_historical_bars(self, ticker: str, limit: int = 250):
        return []

    def fetch_session_bar(self, ticker: str, session_date: str):
        # Has the exact missing session!
        return {
            "ticker": ticker,
            "session_date": session_date,
            "open": 102.0,
            "high": 106.0,
            "low": 101.0,
            "close": 105.0,
            "volume": 2000.0,
            "actual_provider": self.provider_name
        }

class MockFallbackFails(BaseHistoricalProvider):
    @property
    def provider_name(self) -> str:
        return "Mock Fallback (Fails)"

    def fetch_historical_bars(self, ticker: str, limit: int = 250):
        return []

    def fetch_session_bar(self, ticker: str, session_date: str):
        return None

def test_primary_missing_latest_plus_fallback_has_it_fallback_accepted():
    primary = MockPrimaryMissingLatest()
    fallback = MockFallbackHasLatest()
    mgr = ProviderManager(primary_provider=primary, fallback_providers=[fallback])

    # If the fallback supplies the missing session, it must be merged and accepted
    res = mgr.get_raw_historical_bars("COMI")
    # Latest bar should now be the recovered expected session
    expected_session = get_expected_latest_completed_session()
    assert res["bars"][-1]["session_date"] == expected_session.isoformat()
    assert res["sessions_behind"] == 0
    assert res["status"] == "SUCCESS"
    assert "Mock Fallback" in res["actual_provider"]
    assert "actionable_new_trade" not in res

def test_all_providers_missing_latest_yields_data_not_current():
    primary = MockPrimaryMissingLatest()
    fallback = MockFallbackFails()
    mgr = ProviderManager(primary_provider=primary, fallback_providers=[fallback])

    res = mgr.get_raw_historical_bars("COMI")
    assert res["status"] == "DATA_NOT_CURRENT"
    assert res["sessions_behind"] > 0
    assert res["current_analysis_eligible"] is False
    assert "actionable_new_trade" not in res