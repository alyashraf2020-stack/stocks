import datetime

from app.services.breakout_entry import BreakoutEntryAdvisor
from app.services.indicators import TechnicalIndicatorEngine


def make_bars(count: int = 60, base: float = 6.0):
    bars = []
    start = datetime.date(2026, 7, 1)
    for i in range(count):
        close = base + (i * 0.02)
        bars.append({
            "session_date": (start + datetime.timedelta(days=i)).isoformat(),
            "open": close - 0.03,
            "high": close + 0.08,
            "low": close - 0.08,
            "close": close,
            "volume": 100000 + (i * 1000),
        })
    return TechnicalIndicatorEngine.compute_all_indicators(bars)


def test_breakout_levels_are_eod_derived_and_manual_price_does_not_change_them():
    bars = make_bars()
    first = BreakoutEntryAdvisor.evaluate(
        current_price=7.20,
        analytical_bars=bars,
        sessions_behind=0,
    )
    second = BreakoutEntryAdvisor.evaluate(
        current_price=8.20,
        analytical_bars=bars,
        sessions_behind=0,
    )

    assert first["status"] == "VALID"
    assert first["trigger_price"] == second["trigger_price"]
    assert first["entry_zone_min"] == second["entry_zone_min"]
    assert first["entry_zone_max"] == second["entry_zone_max"]
    assert first["stop_loss"] == second["stop_loss"]
    assert first["uses_manual_price_for_levels"] is False


def test_breakout_wait_then_enter_then_do_not_chase():
    bars = make_bars()
    seed = BreakoutEntryAdvisor.evaluate(
        current_price=1.0,
        analytical_bars=bars,
        sessions_behind=0,
    )
    trigger = seed["trigger_price"]
    entry_max = seed["entry_zone_max"]

    waiting = BreakoutEntryAdvisor.evaluate(
        current_price=trigger - 0.01,
        analytical_bars=bars,
        sessions_behind=0,
    )
    assert waiting["decision"] == "WAIT_FOR_BREAKOUT"
    assert waiting["actionable"] is False

    entering = BreakoutEntryAdvisor.evaluate(
        current_price=(trigger + entry_max) / 2,
        analytical_bars=bars,
        sessions_behind=0,
    )
    assert entering["decision"] == "ENTER_BREAKOUT"
    assert entering["actionable"] is True

    chase = BreakoutEntryAdvisor.evaluate(
        current_price=entry_max + 0.01,
        analytical_bars=bars,
        sessions_behind=0,
    )
    assert chase["decision"] == "DO_NOT_CHASE_BREAKOUT"
    assert chase["actionable"] is False


def test_owner_gets_add_on_breakout_label():
    bars = make_bars()
    seed = BreakoutEntryAdvisor.evaluate(
        current_price=1.0,
        analytical_bars=bars,
        sessions_behind=0,
        owns_stock=True,
    )
    price = (seed["trigger_price"] + seed["entry_zone_max"]) / 2
    result = BreakoutEntryAdvisor.evaluate(
        current_price=price,
        analytical_bars=bars,
        sessions_behind=0,
        owns_stock=True,
    )

    assert result["decision"] == "ADD_ON_BREAKOUT"
    assert result["actionable"] is True


def test_sell_dominant_depth_blocks_actionable_breakout():
    bars = make_bars()
    seed = BreakoutEntryAdvisor.evaluate(
        current_price=1.0,
        analytical_bars=bars,
        sessions_behind=0,
    )
    price = (seed["trigger_price"] + seed["entry_zone_max"]) / 2

    result = BreakoutEntryAdvisor.evaluate(
        current_price=price,
        analytical_bars=bars,
        sessions_behind=0,
        market_depth={"status": "MANUAL_INPUT", "pressure": "SELL_DOMINANT"},
    )

    assert result["decision"] == "WAIT_BREAKOUT_CONFIRMATION"
    assert result["actionable"] is False


def test_stale_data_blocks_breakout():
    bars = make_bars()
    result = BreakoutEntryAdvisor.evaluate(
        current_price=7.20,
        analytical_bars=bars,
        sessions_behind=1,
    )

    assert result["status"] == "DATA_NOT_CURRENT"
    assert result["actionable"] is False
