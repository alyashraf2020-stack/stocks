import datetime

from app.services.owner_add_on import OwnerAddOnAdvisor
from app.services.market_depth import MarketDepthService
from app.services.corporate_events import CorporateEventService


def sample_plan():
    return {
        "entry_zone_min": 6.40,
        "entry_zone_max": 6.65,
        "stop_loss": 6.10,
        "target_1": 7.48,
        "target_2": 8.03,
        "target_3": 8.58,
        "plan_status": "ACTIVE",
        "new_entry_allowed": True,
    }


def test_owner_add_on_waits_above_zone():
    result = OwnerAddOnAdvisor.evaluate(
        current_price=7.20,
        capital=100000.0,
        shares_owned=322,
        trade_plan=sample_plan(),
        sessions_behind=0,
    )
    assert result["decision"] in ("WAIT_TO_ADD", "NO_ADD_CAPACITY")
    assert result["decision"] != "ADD_NOW"


def test_owner_add_on_can_add_inside_zone_when_capacity_exists():
    result = OwnerAddOnAdvisor.evaluate(
        current_price=6.50,
        capital=100000.0,
        shares_owned=100,
        trade_plan=sample_plan(),
        sessions_behind=0,
    )
    assert result["decision"] == "ADD_NOW"
    assert result["sizing"]["suggested_add_on_shares"] > 0


def test_owner_add_on_blocks_stale_data():
    result = OwnerAddOnAdvisor.evaluate(
        current_price=6.50,
        capital=100000.0,
        shares_owned=100,
        trade_plan=sample_plan(),
        sessions_behind=1,
    )
    assert result["decision"] == "DATA_NOT_CURRENT"


def test_market_depth_manual_imbalance():
    result = MarketDepthService.summarize(150000, 90000)
    assert result["status"] == "MANUAL_INPUT"
    assert result["pressure"] == "BUY_DOMINANT"
    assert result["imbalance_pct"] == 25.0


def test_market_depth_never_fabricates_missing_values():
    result = MarketDepthService.summarize(None, None)
    assert result["status"] == "UNAVAILABLE"
    assert result["buy_qty"] is None
    assert result["sell_qty"] is None


def test_kora_assembly_event_is_visible_on_event_day():
    events = CorporateEventService.get_relevant_events("KORA", datetime.date(2026, 9, 14))
    assert len(events) == 1
    assert events[0]["event_type"] == "EXTRAORDINARY_GENERAL_ASSEMBLY"
    assert events[0]["impact_bias"] == "UNCERTAIN"
    assert events[0]["days_to_event"] == 0
