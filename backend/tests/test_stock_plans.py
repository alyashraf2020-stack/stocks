import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity
from app.schemas.stock_plans import StockPlanResponse, StockPlansResponse
from app.services.egx_calendar import CAIRO_TZ, is_egx_trading_day, calculate_sessions_behind
from app.services.indicators import TechnicalIndicatorEngine
from app.services.stock_plans import StockPlansService
from app.services.trade_plan import TradePlanEngine
from app.services.data_provider.manager import default_provider_manager
import app.services.stock_plans as plans_module
import app.services.data_provider.manager as manager_module
import app.api.v1.endpoints.stock_plans as endpoint_module

EXPECTED = datetime.date(2026, 10, 5)


@pytest.fixture(autouse=True)
def freeze_session_and_forbid_network(monkeypatch):
    as_of = datetime.datetime(2026, 10, 6, 3, tzinfo=CAIRO_TZ)
    monkeypatch.setattr(plans_module, "get_expected_latest_completed_session", lambda: EXPECTED)
    monkeypatch.setattr(manager_module, "get_expected_latest_completed_session", lambda now=None: EXPECTED)
    monkeypatch.setattr(plans_module, "calculate_sessions_behind", lambda date: calculate_sessions_behind(date, as_of))
    monkeypatch.setattr(manager_module, "calculate_sessions_behind", lambda date, now=None: calculate_sessions_behind(date, as_of))
    monkeypatch.setattr(default_provider_manager, "_fetch_provider_bars", Mock(side_effect=AssertionError("Unexpected network request")))


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def security(db, ticker="COMI", status="ACTIVE"):
    row = EGXSecurity(ticker=ticker, arabic_name=f"شركة {ticker}", english_name=ticker,
                      sector="البنوك", listing_status=status, source_updated_at="2026-10-05")
    db.add(row)
    db.commit()
    return row


def bars(ticker="COMI", end=EXPECTED, count=60, base=100):
    dates = []
    while len(dates) < count:
        if is_egx_trading_day(end):
            dates.append(end.isoformat())
        end -= datetime.timedelta(days=1)
    return [{"ticker": ticker, "session_date": date, "open": base + i * 0.1,
             "high": base + i * 0.1 + 1, "low": base + i * 0.1 - 1,
             "close": base + i * 0.1, "volume": 100000, "actual_provider": "TEST_DATA"}
            for i, date in enumerate(reversed(dates))]


def cache(db, items):
    for bar in items:
        db.add(EGXCandle(**bar))
    db.commit()


def test_overview_keeps_every_stock_without_provider_calls(db):
    for i in range(205):
        security(db, f"S{i}")
    result = StockPlansResponse.model_validate(StockPlansService.overview(db))
    assert result.total == len(result.items) == 205
    assert all(row.status == "DATA_UNAVAILABLE" and row.trade_plan is None for row in result.items)
    default_provider_manager._fetch_provider_bars.assert_not_called()


def test_fresh_plans_match_existing_engine_and_are_not_live_orders(db):
    sec = security(db)
    raw = bars()
    cache(db, raw)
    result = StockPlanResponse.model_validate(StockPlansService.build(db, sec))
    expected = TradePlanEngine.calculate_trade_plan(TechnicalIndicatorEngine.compute_all_indicators(raw), 0)["trade_plan"]
    assert result.status == "PLAN_AVAILABLE"
    assert result.trade_plan.stop_loss == expected["stop_loss"]
    assert result.trade_plan.entry_zone_min == expected["entry_zone_min"]
    assert result.trade_plan.target_3 == expected["target_3"]
    assert result.breakout_entry.stop_loss < result.breakout_entry.entry_zone_min
    assert result.breakout_entry.actionable is False
    assert result.price_basis == "LAST_COMPLETED_SESSION_CLOSE"
    assert result.latest_available_session == EXPECTED.isoformat()


@pytest.mark.parametrize("count,end,status", [
    (60, datetime.date(2026, 10, 4), "DATA_NOT_CURRENT"),
    (10, EXPECTED, "INSUFFICIENT_DATA"),
])
def test_stale_and_short_history_have_no_entry_or_stop(db, count, end, status):
    sec = security(db)
    cache(db, bars(count=count, end=end))
    result = StockPlansService.build(db, sec)
    assert result["status"] == status
    assert result["trade_plan"] is None and result["breakout_entry"] is None


def test_future_bar_cannot_fill_missing_completed_session(db):
    sec = security(db)
    raw = bars(end=datetime.date(2026, 10, 4))
    future = {**raw[-1], "session_date": "2026-10-07"}
    cache(db, raw + [future])
    result = StockPlansService.build(db, sec)
    assert result["status"] == "DATA_NOT_CURRENT"
    assert result["latest_available_session"] == "2026-10-04"
    assert result["trade_plan"] is None


def test_invalid_latest_bar_does_not_make_the_plan_current(db):
    sec = security(db)
    raw = bars()
    raw[-1]["high"] = raw[-1]["close"] - 0.5
    cache(db, raw)
    result = StockPlansService.build(db, sec)
    assert result["status"] == "DATA_NOT_CURRENT"
    assert result["trade_plan"] is None


def test_suspect_cached_tail_is_ignored_without_deleting_it(db):
    sec = security(db)
    raw = bars()
    raw[-1].update({"open": 300, "high": 301, "low": 299, "close": 300})
    cache(db, raw)
    result = StockPlansService.build(db, sec)
    assert result["status"] == "DATA_NOT_CURRENT"
    assert db.query(EGXCandle).count() == 60
    default_provider_manager._fetch_provider_bars.assert_not_called()


def test_inactive_stock_is_visible_without_a_trade_plan(db):
    sec = security(db, status="SUSPENDED")
    cache(db, bars())
    result = StockPlansService.build(db, sec)
    assert result["status"] == "INACTIVE_SECURITY"
    assert result["trade_plan"] is None


def test_one_bad_stock_does_not_break_the_directory(db, monkeypatch):
    security(db, "BAD")
    security(db, "GOOD")
    cache(db, bars("BAD") + bars("GOOD"))
    original = TechnicalIndicatorEngine.compute_all_indicators

    def compute(raw):
        if raw[0]["ticker"] == "BAD":
            raise ValueError("bad stock")
        return original(raw)

    monkeypatch.setattr(TechnicalIndicatorEngine, "compute_all_indicators", compute)
    result = StockPlansService.overview(db)
    statuses = {row["ticker"]: row["status"] for row in result["items"]}
    assert statuses == {"BAD": "ERROR", "GOOD": "PLAN_AVAILABLE"}


def test_missing_source_freshness_does_not_bypass_the_date_gate(db, monkeypatch):
    sec = security(db)
    monkeypatch.setattr(default_provider_manager, "get_analytical_bars", lambda *args, **kwargs:
                        {"bars": [], "sessions_behind": None})
    result = StockPlansService.build(db, sec)
    assert result["status"] == "DATA_UNAVAILABLE"
    assert result["trade_plan"] is None


def test_api_refresh_uses_provider_only_when_requested_and_rejects_foreign_stock(db, monkeypatch):
    security(db)
    calls = []

    def get_data(ticker, **kwargs):
        calls.append(kwargs["allow_network"])
        return {"bars": bars(ticker), "sessions_behind": 0, "actual_provider": "TEST_DATA"}

    monkeypatch.setattr(default_provider_manager, "get_analytical_bars", get_data)
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/api/v1/egx/plans")
        assert response.status_code == 200 and response.json()["total"] == 1
        assert client.post("/api/v1/egx/plans/COMI/refresh").status_code == 200
        assert calls == [False, True]
        assert client.post("/api/v1/egx/plans/AAPL/refresh").status_code == 404
        for _ in range(3):
            endpoint_module.refresh_slots.acquire()
        try:
            assert client.post("/api/v1/egx/plans/COMI/refresh").status_code == 429
            assert calls == [False, True]
        finally:
            for _ in range(3):
                endpoint_module.refresh_slots.release()
    finally:
        app.dependency_overrides.clear()
