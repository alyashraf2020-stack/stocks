from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.schemas.live_analysis import LiveAnalysisRequest, OwnerAddOnSizingResponse
from app.services.owner_add_on import OwnerAddOnAdvisor
from app.services.data_provider.manager import default_provider_manager
from tests.test_owner_add_on_and_context import sample_plan
from tests.test_stock_plans import db, security, bars, cache, freeze_session_and_forbid_network


def evaluate(**overrides):
    values = dict(current_price=6.5, capital=100000, shares_owned=100, buy_price=6,
                  trade_plan=sample_plan(), sessions_behind=0, add_on_cash=1000)
    values.update(overrides)
    result = OwnerAddOnAdvisor.evaluate(**values)
    if result['sizing']:
        OwnerAddOnSizingResponse.model_validate(result['sizing'])
    return result


def test_cash_limited_quantity_cost_and_weighted_average():
    result = evaluate()
    size = result['sizing']
    assert result['decision'] == 'ADD_NOW'
    assert size['suggested_add_on_shares'] == size['executable_add_on_shares'] == 153
    assert size['estimated_add_on_value_egp'] == 994.5
    assert size['remaining_cash_after_add_on_egp'] == 5.5
    assert size['shares_after_add_on'] == 253
    assert size['average_buy_price_after_add_on'] == pytest.approx((600 + 994.5) / 253, abs=0.00005)
    assert size['limiting_factors'] == ['CASH']
    assert size['position_value_after_add_on_egp'] == 1644.5
    assert size['risk_to_stop_after_add_on_egp'] == 101.2


def test_allocation_is_a_separate_limit_from_available_cash():
    size = evaluate(capital=10000, shares_owned=300)['sizing']
    assert size['max_total_allocation_egp'] == 2000
    assert size['current_position_value_egp'] == 1950
    assert size['remaining_allocation_egp'] == 50
    assert size['suggested_add_on_shares'] == 7
    assert size['limiting_factors'] == ['ALLOCATION']
    assert size['position_value_after_add_on_egp'] <= 2000


def test_risk_limit_is_not_bypassed_by_more_cash():
    plan = {**sample_plan(), 'stop_loss': 5.0}
    size = evaluate(capital=10000, shares_owned=50, trade_plan=plan)['sizing']
    assert size['suggested_add_on_shares'] == 50
    assert size['limiting_factors'] == ['RISK']
    assert size['risk_to_stop_after_add_on_egp'] == size['max_risk_allowed_egp'] == 150


def test_zero_capacity_explains_both_exhausted_limits_with_actual_amounts():
    result = evaluate(capital=1000, add_on_cash=100)
    assert result['decision'] == 'NO_ADD_CAPACITY'
    assert result['sizing']['suggested_add_on_shares'] == 0
    assert result['sizing']['remaining_allocation_egp'] == 0
    assert result['sizing']['remaining_risk_budget_egp'] == 0
    assert all(value in result['reason_ar'] for value in ['650.00', '200.00', '40.00', '15.00'])


@pytest.mark.parametrize('cash', [0, 6.49])
def test_explicit_cash_zero_or_less_than_one_share_is_not_missing(cash):
    result = evaluate(add_on_cash=cash)
    assert result['decision'] == 'NO_ADD_CAPACITY'
    assert result['sizing']['cash_constraint_applied'] is True
    assert result['sizing']['suggested_add_on_shares'] == 0
    assert result['sizing']['available_add_on_cash_egp'] == cash


def test_unspecified_cash_does_not_issue_an_executable_quantity():
    result = evaluate(add_on_cash=None)
    assert result['decision'] == 'CASH_NOT_SPECIFIED'
    assert result['sizing']['suggested_add_on_shares'] > 0
    assert result['sizing']['executable_add_on_shares'] == 0
    assert result['sizing']['available_add_on_cash_egp'] is None


@pytest.mark.parametrize('owned', [None, 0, -1, 3.7, float('nan'), True])
def test_missing_or_invalid_quantity_is_not_a_zero_position(owned):
    result = evaluate(shares_owned=owned)
    assert result['decision'] == 'MISSING_POSITION_DATA'
    assert result['sizing'] is None


@pytest.mark.parametrize('delay', [1, None])
def test_unknown_or_stale_session_cannot_allow_add_on(delay):
    assert evaluate(sessions_behind=delay)['decision'] == 'DATA_NOT_CURRENT'


@pytest.mark.parametrize('price', [6.2, 7.2])
def test_conditional_scenario_has_no_execution_and_conservative_hold_valuation(price):
    result = evaluate(current_price=price)
    size = result['sizing']
    assert result['decision'] in ('WAIT_TO_ADD', 'WAIT_CONFIRMATION')
    assert size['sizing_price'] == 6.65
    assert size['valuation_price'] == max(price, 6.65)
    assert size['executable_add_on_shares'] == 0
    assert size['suggested_add_on_shares'] > 0


def test_broken_stop_takes_precedence_over_empty_budget():
    result = evaluate(current_price=6, add_on_cash=0)
    assert result['decision'] == 'DO_NOT_ADD'
    assert result['sizing'] is None


@pytest.mark.parametrize('state', ['INVALIDATED', 'TARGETS_COMPLETED', 'NO_VALID_SETUP'])
def test_expired_plan_cannot_recommend_adding(state):
    result = evaluate(trade_plan={**sample_plan(), 'plan_status': state})
    assert result['decision'] in ('DO_NOT_ADD', 'NO_VALID_SETUP')
    assert result['sizing'] is None
    if result['sizing']:
        assert result['sizing']['executable_add_on_shares'] == 0


def test_absent_purchase_price_has_no_invented_weighted_average():
    size = evaluate(buy_price=None)['sizing']
    assert size['average_buy_price_after_add_on'] is None


def test_decimal_floor_preserves_exact_whole_share_boundary():
    result = evaluate(current_price=.3, capital=1000, add_on_cash=.9, buy_price=.25,
                      shares_owned=1, trade_plan={**sample_plan(), 'entry_zone_min': .2, 'entry_zone_max': .3, 'stop_loss': .1})
    assert result['sizing']['shares_by_cash'] == 3
    assert result['sizing']['suggested_add_on_shares'] == 3


@pytest.mark.parametrize('changes', [{'add_on_cash': -1}, {'add_on_cash': 100001}, {'shares_owned': 3.7},
                                   {'shares_owned': 0}, {'shares_owned': True}, {'buy_price': -1}, {'capital': float('inf')}])
def test_request_rejects_bad_funding_or_position_values(changes):
    with pytest.raises(ValidationError):
        LiveAnalysisRequest.model_validate({'ticker': 'COMI', 'current_price': 6.5, 'capital': 100000,
                                            'owns_stock': True, 'shares_owned': 100, **changes})


def test_live_api_passes_cash_and_purchase_price_to_calculator(db, monkeypatch):
    import app.api.v1.endpoints.live_analysis as endpoint
    security(db)
    raw = bars(count=60)
    monkeypatch.setattr(default_provider_manager, 'get_analytical_bars', Mock(return_value={'bars': raw, 'sessions_behind': 0}))
    monkeypatch.setattr(endpoint.LiveDecisionEngine, 'evaluate', Mock(return_value={
        'ticker': 'COMI', 'current_price': 6.5, 'decision': 'HOLD', 'decision_ar': 'احتفاظ',
        'badge_color': 'blue', 'actionable_new_trade': False, 'current_analysis_eligible': True,
        'reason_ar': 'TEST', 'status': 'VALID', 'owns_stock': True, 'buy_price': 6, 'shares_owned': 100,
        'trade_plan': sample_plan(),
    }))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post('/api/v1/egx/live-analysis', json={'ticker': 'COMI', 'current_price': 6.5, 'capital': 100000,
                                                              'owns_stock': True, 'buy_price': 6, 'shares_owned': 100, 'add_on_cash': 1000})
        assert response.status_code == 200
        size = response.json()['owner_add_on']['sizing']
        assert size['suggested_add_on_shares'] == 153
        assert size['average_buy_price_after_add_on'] == 6.3024
        response = client.post('/api/v1/egx/live-analysis', json={'ticker': 'COMI', 'current_price': 6.5, 'capital': 100000,
                                                              'owns_stock': True, 'buy_price': 6, 'shares_owned': 100, 'add_on_cash': 0})
        assert response.status_code == 200
        assert response.json()['owner_add_on']['sizing']['suggested_add_on_shares'] == 0
    finally:
        app.dependency_overrides.clear()
