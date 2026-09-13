import pytest
from app.services.trade_plan import TradePlanEngine
from app.services.risk_manager import RiskManager
from app.services.decision_engine import LiveDecisionEngine
from app.services.indicators import TechnicalIndicatorEngine

@pytest.fixture
def sample_valid_bars():
    bars = []
    base_price = 100.0
    for i in range(60):
        c = base_price + (i * 0.5)
        bars.append({
            "session_date": f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}",
            "open": c - 0.5,
            "high": c + 1.5,
            "low": c - 1.0,
            "close": c,
            "volume": 100000.0,
            "hlcv_status": "VALID"
        })
    return TechnicalIndicatorEngine.compute_all_indicators(bars)

def test_trade_plan_geometry(sample_valid_bars):
    # Under Zero-Session-Lag policy, valid trade plan requires sessions_behind == 0
    res = TradePlanEngine.calculate_trade_plan(sample_valid_bars, sessions_behind=0)
    assert res["status"] == "VALID"
    assert res["actionable_new_trade"] is True
    plan = res["trade_plan"]
    
    stop = plan["stop_loss"]
    e_min = plan["entry_zone_min"]
    e_max = plan["entry_zone_max"]
    t1 = plan["target_1"]
    t2 = plan["target_2"]
    t3 = plan["target_3"]
    r = plan["r_unit"]

    assert stop < e_min <= e_max
    assert e_max < t1 < t2 < t3
    assert t1 == pytest.approx(e_max + (1.5 * r), 0.01)
    assert t2 == pytest.approx(e_max + (2.5 * r), 0.01)
    assert t3 == pytest.approx(e_max + (3.5 * r), 0.01)
    assert "الدعم" in plan["entry_basis"]
    assert "وقف" in plan["stop_basis"]

def test_risk_management_strict_caps():
    capital = 100000.0
    planning_entry = 100.0
    stop_loss = 90.0
    
    sizing = RiskManager.calculate_position_sizing(capital, planning_entry, stop_loss)
    assert sizing["suggested_shares"] == 150
    assert sizing["max_expected_loss_egp"] == 1500.0
    assert sizing["actual_risk_pct"] <= 1.5
    assert sizing["actual_allocation_pct"] <= 20.0

def test_risk_management_allocation_binding():
    capital = 100000.0
    planning_entry = 100.0
    stop_loss = 99.0
    
    sizing = RiskManager.calculate_position_sizing(capital, planning_entry, stop_loss)
    assert sizing["suggested_shares"] == 200
    assert sizing["position_value_egp"] == 20000.0
    assert sizing["actual_allocation_pct"] <= 20.0
    assert sizing["max_expected_loss_egp"] <= 1500.0

def test_decision_non_owner_scenarios(sample_valid_bars):
    plan_res = TradePlanEngine.calculate_trade_plan(sample_valid_bars, sessions_behind=0)
    plan = plan_res["trade_plan"]
    e_min = plan["entry_zone_min"]
    e_max = plan["entry_zone_max"]
    stop = plan["stop_loss"]

    # 1. Price inside entry zone -> ENTER_NOW
    inside_price = (e_min + e_max) / 2.0
    res_enter = LiveDecisionEngine.evaluate("COMI", inside_price, 100000.0, owns_stock=False, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_enter["decision"] == "ENTER_NOW"
    assert "دخول الآن" in res_enter["decision_ar"]

    # 2. Price above entry zone -> WAIT (Score alone NEVER overrides this!)
    above_price = e_max + 5.0
    res_wait = LiveDecisionEngine.evaluate("COMI", above_price, 100000.0, owns_stock=False, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_wait["decision"] == "WAIT"
    assert "انتظار" in res_wait["decision_ar"]

    # 3. Price below stop -> DO_NOT_ENTER
    below_stop = stop - 1.0
    res_avoid = LiveDecisionEngine.evaluate("COMI", below_stop, 100000.0, owns_stock=False, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_avoid["decision"] == "DO_NOT_ENTER"
    assert "لا تدخل" in res_avoid["decision_ar"]

def test_decision_existing_position_scenarios(sample_valid_bars):
    plan_res = TradePlanEngine.calculate_trade_plan(sample_valid_bars, sessions_behind=0)
    plan = plan_res["trade_plan"]
    stop = plan["stop_loss"]
    t1 = plan["target_1"]
    t2 = plan["target_2"]
    t3 = plan["target_3"]

    # Stop hit -> EXIT_STOP_LOSS
    res_exit = LiveDecisionEngine.evaluate("COMI", stop - 0.5, 100000.0, owns_stock=True, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_exit["decision"] == "EXIT_STOP_LOSS"

    # T1 reached -> TAKE_PARTIAL_PROFIT
    res_t1 = LiveDecisionEngine.evaluate("COMI", t1 + 0.1, 100000.0, owns_stock=True, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_t1["decision"] == "TAKE_PARTIAL_PROFIT"

    # T2 reached -> RAISE_STOP_LOSS
    res_t2 = LiveDecisionEngine.evaluate("COMI", t2 + 0.1, 100000.0, owns_stock=True, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_t2["decision"] == "RAISE_STOP_LOSS"

    # T3 reached -> TAKE_PROFIT (TARGETS_COMPLETED)
    res_t3 = LiveDecisionEngine.evaluate("COMI", t3 + 0.1, 100000.0, owns_stock=True, analytical_bars=sample_valid_bars, sessions_behind=0)
    assert res_t3["decision"] == "TAKE_PROFIT"
    assert res_t3["plan_status"] == "TARGETS_COMPLETED"
    assert res_t3["new_entry_allowed"] is False

def test_decision_stale_data_gate(sample_valid_bars):
    # Under Zero-Session-Lag policy, sessions_behind > 0 must return DATA_NOT_CURRENT
    res = LiveDecisionEngine.evaluate("COMI", 120.0, 100000.0, owns_stock=False, analytical_bars=sample_valid_bars, sessions_behind=1)
    assert res["decision"] == "DATA_NOT_CURRENT"
    assert "بيانات آخر جلسة غير متاحة" in res["reason_ar"]

def test_decision_insufficient_history_gate():
    short_bars = [{"session_date": f"2026-01-{i+1:02d}", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0} for i in range(10)]
    res = LiveDecisionEngine.evaluate("COMI", 10.0, 100000.0, owns_stock=False, analytical_bars=short_bars, sessions_behind=0)
    assert res["decision"] == "INSUFFICIENT_DATA"

def test_kora_regression_targets_completed():
    # KORA setup regression test
    # entry_max = 3.64, target_1 = 4.45, target_2 = 4.99, target_3 = 5.53, manual_current_price = 6.82
    bars = []
    base = 3.30
    for i in range(60):
        bars.append({
            "session_date": f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}",
            "open": base,
            "high": base + 0.35,
            "low": base - 0.05,
            "close": base + 0.1,
            "volume": 50000.0,
            "hlcv_status": "VALID"
        })
    computed = TechnicalIndicatorEngine.compute_all_indicators(bars)

    # 1. Non-owner at 6.82
    res_non_owner = LiveDecisionEngine.evaluate(
        ticker="KORA",
        current_price=6.82,
        capital=100000.0,
        owns_stock=False,
        analytical_bars=computed,
        sessions_behind=0
    )
    assert res_non_owner["plan_status"] == "TARGETS_COMPLETED"
    assert res_non_owner["new_entry_allowed"] is False
    assert res_non_owner["decision"] == "DO_NOT_CHASE"
    assert "لا تدخل الآن" in res_non_owner["decision_ar"]
    assert "تجاوز جميع أهداف الخطة السابقة" in res_non_owner["reason_ar"]

    # 2. Owner at 6.82
    res_owner = LiveDecisionEngine.evaluate(
        ticker="KORA",
        current_price=6.82,
        capital=100000.0,
        owns_stock=True,
        analytical_bars=computed,
        sessions_behind=0
    )
    assert res_owner["plan_status"] == "TARGETS_COMPLETED"
    assert res_owner["decision"] == "TAKE_PROFIT"
    assert "جني أرباح" in res_owner["decision_ar"]

def test_owner_mode_metrics_and_sizing_hidden(sample_valid_bars):
    # When owns_stock = True:
    # suggested_shares / new trade sizing must be None, and owner attributes present
    res_owner = LiveDecisionEngine.evaluate(
        ticker="COMI",
        current_price=105.0,
        capital=100000.0,
        owns_stock=True,
        buy_price=100.0,
        shares_owned=500,
        analytical_bars=sample_valid_bars,
        sessions_behind=0
    )
    assert res_owner["owns_stock"] is True
    assert res_owner["buy_price"] == 100.0
    assert res_owner["shares_owned"] == 500
    assert res_owner["position_sizing"] is None

    # When owns_stock = False:
    # New trade position sizing must be present
    res_non_owner = LiveDecisionEngine.evaluate(
        ticker="COMI",
        current_price=105.0,
        capital=100000.0,
        owns_stock=False,
        analytical_bars=sample_valid_bars,
        sessions_behind=0
    )
    assert res_non_owner["owns_stock"] is False
    assert res_non_owner["position_sizing"] is not None
    assert res_non_owner["position_sizing"]["suggested_shares"] > 0