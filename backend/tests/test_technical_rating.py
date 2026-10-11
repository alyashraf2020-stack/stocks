import copy
import datetime
import json
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.schemas.stock_plans import StockPlanResponse
from app.services.indicators import TechnicalIndicatorEngine
from app.services.smoothing import rsi, wilder
from app.services.stock_plans import StockPlansService
from app.services.seeder import seed_security_master
from app.models.security import EGXSecurity
from app.services.technical_rating import TechnicalRatingEngine
from app.services.data_provider.manager import default_provider_manager
from tests.test_stock_plans import db, freeze_session_and_forbid_network, security, bars, cache, EXPECTED


def flat_bars(count=250):
    raw = bars(count=count)
    for row in raw:
        row.update(open=100, high=100, low=100, close=100, volume=1000)
    return raw


def test_wilder_rsi_matches_published_worked_example():
    closes = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00])
    output = rsi(closes)
    assert output.iloc[:14].isna().all()
    assert output.iloc[14] == pytest.approx(70.464135, abs=1e-6)
    assert output.iloc[15] == pytest.approx(66.249619, abs=1e-6)


def test_wilder_atr_uses_arithmetic_seed_then_recursive_average():
    series = pd.Series([float(i) for i in range(1, 17)])
    output = wilder(series)
    assert output.iloc[:13].isna().all()
    assert output.iloc[13] == 7.5
    assert output.iloc[14] == pytest.approx((7.5 * 13 + 15) / 14)
    assert output.iloc[15] == pytest.approx((output.iloc[14] * 13 + 16) / 14)


def test_fresh_database_seeds_with_runtime_autoflush_disabled(db):
    db.autoflush = False
    count = seed_security_master(db)
    assert count >= 179
    assert db.get(EGXSecurity, "BIOC").isin == "EGS38171C012"
    assert seed_security_master(db) == count


def test_flat_market_has_26_neutral_votes_not_a_strong_buy():
    result = TechnicalRatingEngine.calculate(flat_bars(), current=True)
    assert result["score"] == 0
    assert result["signal"] == "NEUTRAL"
    assert result["counts"] == {"BUY": 0, "SELL": 0, "NEUTRAL": 26}
    assert result["available_count"] == 26
    assert result["atr_pct"] == 0
    assert result["status"] == "COMPLETE"
    assert next(item for item in result["indicators"] if item["key"] == "RSI14")["value"] == 50
    enriched = TechnicalIndicatorEngine.compute_all_indicators(flat_bars())
    assert enriched[-1]["rsi_14"] == 50
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("count,available", [(49, None), (50, 22), (100, 24), (200, 26)])
def test_warmup_is_counted_honestly(count, available):
    result = TechnicalRatingEngine.calculate(flat_bars(count))
    if available is None:
        assert result is None
    else:
        assert result["available_count"] == available
        assert result["coverage_pct"] == pytest.approx(100 * available / 26, abs=0.01)
        assert sum(result["counts"].values()) == available
        unavailable = [row["key"] for row in result["indicators"] if row["vote"] is None]
        if count < 200:
            assert "EMA200" in unavailable and "SMA200" in unavailable


def test_score_is_group_balanced_and_not_probability():
    result = TechnicalRatingEngine.calculate(bars(count=250), current=True)
    means = []
    for group in ("TREND", "MOMENTUM"):
        votes = [row["vote"] for row in result["indicators"] if row["group"] == group and row["vote"] is not None]
        means.append(sum(votes) / len(votes))
    assert result["score"] == pytest.approx(100 * sum(means) / 2, abs=0.01)
    assert -100 <= result["score"] <= 100
    assert "confidence" not in result and "win_probability" not in result
    assert "احتمال الربح" in result["note_ar"]
    assert len({row["key"] for row in result["indicators"]}) == 26


def test_rating_is_invariant_to_price_unit_scaling():
    raw = bars(count=250)
    scaled = copy.deepcopy(raw)
    for row in scaled:
        for key in ("open", "high", "low", "close"):
            row[key] *= 37
    before, after = TechnicalRatingEngine.calculate(raw), TechnicalRatingEngine.calculate(scaled)
    assert before["counts"] == after["counts"]
    assert before["score"] == after["score"]
    assert before["atr_pct"] == pytest.approx(after["atr_pct"], abs=1e-5)
    assert before["daily_change_pct"] == pytest.approx(after["daily_change_pct"], abs=1e-5)


def test_zero_volume_is_not_invented_for_volume_indicators():
    raw = flat_bars()
    for row in raw:
        row["volume"] = 0
    result = TechnicalRatingEngine.calculate(raw)
    unavailable = {row["key"] for row in result["indicators"] if row["vote"] is None}
    assert unavailable == {"VWMA20", "MFI14"}
    assert result["relative_volume"] is None
    assert result["available_count"] == 24
    assert result["score"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("direction", [1, -1])
def test_trend_direction_and_per_stock_values(direction):
    raw = bars(count=250)
    for i, row in enumerate(raw):
        value = 100 + direction * i * 0.1
        row.update(open=value, high=value + 1, low=value - 1, close=value)
    result = TechnicalRatingEngine.calculate(raw)
    # HMA9 exactly tracks a linear ramp; the other thirteen averages lag it.
    assert result["trend_score"] == pytest.approx(direction * 100 * 13 / 14, abs=0.01)
    assert result["daily_change"] == pytest.approx(direction * 0.1)
    assert result["score"] * direction > 0


def test_report_metrics_match_actual_plan_entry_not_current_close(db):
    sec = security(db)
    cache(db, bars(count=250))
    result = StockPlanResponse.model_validate(StockPlansService.build(db, sec))
    plan, metrics = result.trade_plan, result.plan_metrics
    assert result.technical_rating.is_current
    assert result.technical_rating.available_count == 26
    assert metrics.reference_entry == plan.planning_entry
    assert metrics.risk_pct == pytest.approx(100 * (plan.planning_entry - plan.stop_loss) / plan.planning_entry, abs=0.01)
    assert metrics.reward_risk[0] == pytest.approx((plan.target_1 - plan.planning_entry) / (plan.planning_entry - plan.stop_loss), abs=0.01)
    assert result.technical_rating.as_of_session == result.latest_available_session


def test_stale_rating_is_historical_and_cannot_create_a_current_plan(db):
    sec = security(db)
    cache(db, bars(count=250, end=EXPECTED - datetime.timedelta(days=1)))
    result = StockPlanResponse.model_validate(StockPlansService.build(db, sec))
    assert result.status == "DATA_NOT_CURRENT"
    assert result.trade_plan is None and result.plan_metrics is None
    assert result.technical_rating.is_current is False


def test_short_history_has_no_score_or_fabricated_plan(db):
    sec = security(db)
    cache(db, bars(count=23))
    result = StockPlansService.build(db, sec)
    assert result["technical_rating"] is None
    assert result["trade_plan"] is None
    assert result["status"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), -1])
def test_bad_latest_price_cannot_create_current_rating(db, monkeypatch, bad):
    sec = security(db)
    raw = bars(count=60)
    raw[-1]["close"] = bad
    monkeypatch.setattr(default_provider_manager, "get_analytical_bars", Mock(return_value={"bars": raw}))
    result = StockPlansService.build(db, sec)
    assert result["status"] == "DATA_NOT_CURRENT"
    assert result["technical_rating"]["is_current"] is False
    assert result["trade_plan"] is None


def test_dates_are_unique_and_missing_market_sessions_are_visible(db, monkeypatch):
    sec = security(db)
    raw = bars(count=60)
    raw.pop(20)
    raw.append(dict(raw[-1]))
    monkeypatch.setattr(default_provider_manager, "get_analytical_bars", Mock(return_value={"bars": raw}))
    result = StockPlansService.build(db, sec)
    assert result["analytical_bars_count"] == 59
    assert result["missing_sessions_count"] == 1
    assert result["technical_rating"]["available_count"] == 22


def test_generic_technical_api_and_directory_agree_for_any_stock(db):
    security(db, "RUBX")
    cache(db, bars(ticker="RUBX", count=250))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        report = client.get("/api/v1/egx/stocks/rubx/technical")
        assert report.status_code == 200
        row = next(row for row in client.get("/api/v1/egx/plans").json()["items"] if row["ticker"] == "RUBX")
        assert report.json()["technical_rating"] == row["technical_rating"]
        assert report.json()["trade_plan"] == row["trade_plan"]
        assert client.get("/api/v1/egx/stocks/NOTLISTED/technical").status_code == 404
        default_provider_manager._fetch_provider_bars.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("selected,count,full", [("1W", 5, True), ("1M", 22, True), ("3M", 60, False), ("1Y", 60, False)])
def test_chart_range_change_uses_real_reference_and_marks_partial(db, monkeypatch, selected, count, full):
    import app.api.v1.endpoints.stocks as endpoints
    monkeypatch.setattr(endpoints, "get_expected_latest_completed_session", lambda: EXPECTED)
    monkeypatch.setattr(endpoints, "calculate_sessions_behind", lambda date: 0 if date == EXPECTED else 1)
    security(db)
    raw = bars(count=60)
    for row in raw:
        row["validation_status"] = "VALID"
    monkeypatch.setattr(default_provider_manager, "get_analytical_bars", Mock(return_value={
        "status": "SUCCESS", "bars": raw, "expected_latest_session": EXPECTED.isoformat(),
        "latest_session": EXPECTED.isoformat(), "sessions_behind": 0, "freshness": "CURRENT", "actual_provider": "TEST_DATA",
    }))
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get(f"/api/v1/egx/stocks/COMI/chart?range={selected}")
        assert response.status_code == 200
        result = response.json()
        reference = raw[max(0, 60 - count - 1)]
        assert result["total_bars"] == count
        assert result["range_complete"] == full
        assert result["change_reference_session"] == reference["session_date"]
        assert result["range_change_pct"] == pytest.approx(100 * (raw[-1]["close"] / reference["close"] - 1), abs=0.0001)
        assert result["bars"][-1]["sma_50"] is not None
    finally:
        app.dependency_overrides.clear()
