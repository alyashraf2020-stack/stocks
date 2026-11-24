from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from app.core.database import SessionLocal
from app.main import app
from app.models.risk_settings import RiskSettings
from app.models.security import EGXSecurity
from app.models.sharia_screening import ShariaScreening
from app.schemas.ai_analysis import AnalysisRequest
from app.schemas.risk import Candidate, PortfolioSnapshot, RiskPolicy, ScenarioRequest
from app.schemas.sharia import ScreeningEvidence
from app.schemas.thndr import Holding, Portfolio
from app.services.ai_context_builder import build_analysis
from app.services.ai_opportunities import opportunities
from app.services.portfolio_risk import brokerage_snapshot, summarize, trade_costs
from app.services.risk_policy import calculate_size
from app.services.risk_scenarios import review_position
from app.services.sharia_screening import evaluate_screen
from fastapi.testclient import TestClient
from pydantic import ValidationError

NOW = datetime(2026, 11, 23, 14, tzinfo=timezone.utc)
SOURCE = "https://beta.egx.com.eg/en/disclosures"
KEY = "phase4-owner-gateway-fixture-" + "x" * 32
SECTORS = {"COMI": "Bank", "AMES": "Health", "BIOC": "Health", "SWDY": "Industry"}
CANDIDATE = Candidate(
    ticker="AMES", entry=100, stop=94, target=125, average_turnover=2_000_000
)


def policy(**field):
    return RiskPolicy.model_validate(
        dict(commission_rate="0.002", buy_tax_rate="0.001", sell_tax_rate="0.001")
        | field
    )


def snapshot(**field):
    return PortfolioSnapshot.model_validate(
        dict(
            as_of=NOW,
            equity=100_000,
            settled_cash=10_000,
            buying_power=8_000,
            positions=[
                {
                    "ticker": "BIOC",
                    "shares": 100,
                    "mark": 50,
                    "average_cost": 60,
                    "stop": 47,
                    "sellable_shares": 45,
                }
            ],
            pending_buys=[
                {
                    "ticker": "AMES",
                    "notional": 5000,
                    "reserved_cash": 5100,
                    "planned_risk": 450,
                }
            ],
            adjusted_history=[
                {"day": "2026-11-19", "equity": 101_000},
                {"day": "2026-11-22", "equity": 100_500},
            ],
            adjusted_equity_now=100_000,
        )
        | field
    )


def evidence(**fields):
    values = dict(
        reviewed_on=NOW.date(),
        activity="PERMITTED",
        ordinary_share=True,
        activity_source=SOURCE,
        period_end="2026-09-30",
        financial_source=SOURCE,
        market_value_source=SOURCE,
        total_revenue=100,
        noncompliant_income=5,
        total_assets=100,
        average_market_value=200,
        interest_debt=66,
        interest_investments=66,
        liquid_assets=70,
        index_member=False,
        index_as_of="2026-08-01",
        index_source=SOURCE,
    )
    return ScreeningEvidence.model_validate(values | fields)


def test_decimal_sizing_intersection_counts_reserved_cash_fees_gaps_and_pending_risk():
    p = policy()
    s = snapshot()
    result = calculate_size(CANDIDATE, s, SECTORS, p, "MANUAL", "COMPLIANT", NOW)
    cash, risk, _, fee = trade_costs(
        p, CANDIDATE.entry, CANDIDATE.stop, CANDIDATE.target
    )
    shares = result["shares"]
    assert not result["blockers"] and shares == 48
    assert result["limiting_rule"] == "BUYING_POWER"
    assert result["cash_after"] == D(4900) - cash * shares
    assert result["estimated_fees"] == fee * shares
    assert (
        result["planned_risk"] == risk * shares
        and risk > CANDIDATE.entry - CANDIDATE.stop
    )
    assert result["planned_risk"] + D(450) <= s.equity * D(".015")
    assert result["cash_required"] + 5000 <= D(".20") * s.equity
    assert result["cash_required"] + 10_000 <= D(".30") * s.equity
    assert result["executable"] is False


@pytest.mark.parametrize(
    "change,blocker",
    [
        ({"settled_cash": None}, "SETTLED_CASH_AND_RESERVATIONS"),
        ({"as_of": NOW - timedelta(hours=2)}, "CURRENT_SNAPSHOT"),
        ({"adjusted_history": None}, "DRAWDOWN_HISTORY"),
        ({"adjusted_equity_now": "92000"}, "DAILY_LOSS_LIMIT"),
        (
            {
                "adjusted_history": [
                    {"day": "2026-11-19", "equity": 150000},
                    {"day": "2026-11-22", "equity": 100500},
                ]
            },
            "DRAWDOWN_LIMIT",
        ),
        ({"pending_buys": [{"ticker": "SWDY", "notional": 1000}]}, "PENDING_RISK"),
        (
            {"positions": [{"ticker": "BIOC", "shares": 100, "mark": 50}]},
            "PLANNED_OPEN_RISK",
        ),
        (
            {"positions": [{"ticker": "BIOC", "shares": 100, "mark": 50, "stop": 51}]},
            "POSITION_STOP_BREACHED",
        ),
        (
            {"positions": [{"ticker": "BIOC", "shares": 800, "mark": 50, "stop": 47}]},
            "EXISTING_CONCENTRATION_BREACH",
        ),
    ],
)
def test_unknown_or_breached_portfolio_constraints_fail_closed(change, blocker):
    result = calculate_size(
        CANDIDATE, snapshot(**change), SECTORS, policy(), "MANUAL", None, NOW
    )
    assert blocker in result["blockers"] and result["shares"] is None


@pytest.mark.parametrize(
    "change,blocker",
    [
        ({"kill_switch": True}, "KILL_SWITCH"),
        ({"islamic_mode": True}, "SHARIA_UNVERIFIED"),
        ({"commission_rate": None}, "COST_CONFIGURATION"),
        ({"min_reward_to_risk": 100}, "MINIMUM_REWARD_TO_RISK"),
        ({"min_daily_turnover": 3_000_000}, "MINIMUM_LIQUIDITY"),
    ],
)
def test_policy_constraints(change, blocker):
    result = calculate_size(
        CANDIDATE, snapshot(), SECTORS, policy(**change), "MANUAL", None, NOW
    )
    assert blocker in result["blockers"] and result["shares"] is None


def test_position_count_includes_open_orders_and_reserved_new_risk():
    s = snapshot()
    two_open = policy(max_open_positions=2)
    new = CANDIDATE.model_copy(update={"ticker": "SWDY"})
    assert calculate_size(new, s, SECTORS, two_open, "MANUAL", None, NOW)[
        "blockers"
    ] == ["OPEN_POSITIONS_LIMIT"]
    constrained = policy(max_aggregate_risk=".009")
    result = calculate_size(CANDIDATE, s, SECTORS, constrained, "MANUAL", None, NOW)
    assert result["planned_risk"] <= result["portfolio"]["available_risk_budget"]
    assert result["shares"] < 48


@pytest.mark.parametrize(
    "key,val",
    [
        ("max_trade_risk", ".0150001"),
        ("max_stock_allocation", ".21"),
        ("max_trade_risk", 0),
        ("max_aggregate_risk", "Infinity"),
    ],
)
def test_invalid_policy_boundaries_are_rejected(key, val):
    with pytest.raises(ValidationError):
        policy(**{key: val})


@pytest.mark.parametrize(
    "field,val",
    [
        ("equity", 0),
        ("equity", "NaN"),
        ("settled_cash", -1),
        ("buying_power", "Infinity"),
    ],
)
def test_bad_financial_inputs(field, val):
    with pytest.raises(ValidationError):
        snapshot(**{field: val})


def test_thndr_read_only_snapshot_does_not_infer_settlement_stops_or_history():
    portfolio = Portfolio(
        last_sync=NOW,
        total_value=10_000,
        available_cash=2000,
        open_orders=[],
        holdings=[
            Holding(
                ticker="AMES",
                instrument_id="EGS000",
                quantity=20,
                average_price=30,
                market_value=500,
            )
        ],
    )
    snap = brokerage_snapshot(portfolio, {}, NOW)
    summary = summarize(snap, SECTORS, policy(), "THNDR", NOW)
    assert summary["reported_buying_power"] == 2000
    assert (
        summary["available_cash"] is None and summary["aggregate_position_risk"] is None
    )
    assert summary["daily_loss_ratio"] is None and summary["drawdown_ratio"] is None
    assert summary["stock_values"]["AMES"] is None


def test_scenarios_respect_sellable_shares_and_unsettled_proceeds():
    s = snapshot()
    policy_used = policy()
    summary = summarize(s, SECTORS, policy_used, "MANUAL", NOW)
    position = s.positions[0]
    report = review_position(
        position,
        ScenarioRequest(ticker="BIOC", action="PARTIAL_SELL", shares=40),
        s,
        summary,
        policy_used,
    )
    assert report["risk_after"] < report["risk_before"]
    assert report["unsettled_proceeds"] > 0 and report["remaining_cash"] == 4900
    assert report["revised_average_cost"] == 60
    full = review_position(
        position,
        ScenarioRequest(ticker="BIOC", action="FULL_EXIT"),
        s,
        summary,
        policy_used,
    )
    assert (
        full["limitations"] == ["SELL_SIZE_OR_SETTLEMENT_LIMIT"]
        and full["shares"] is None
    )
    move = review_position(
        position,
        ScenarioRequest(ticker="BIOC", action="MOVE_STOP_LOSS", revised_stop=49),
        s,
        summary,
        policy_used,
    )
    assert move["risk_after"] < move["risk_before"]
    hold = review_position(
        position, ScenarioRequest(ticker="BIOC", action="HOLD"), s, summary, policy_used
    )
    assert hold["risk_before"] == hold["risk_after"]
    add = review_position(
        position,
        ScenarioRequest(ticker="BIOC", action="ADD_TO_POSITION"),
        s,
        summary,
        policy_used,
    )
    assert add["shares"] is None and add["limitations"] == ["NO_ELIGIBLE_ADD_SETUP"]


@pytest.mark.parametrize(
    "changes,outcome",
    [
        ({}, "COMPLIANT"),
        ({"noncompliant_income": "5.0001", "index_member": True}, "NON_COMPLIANT"),
        ({"interest_debt": "66.0001"}, "NON_COMPLIANT"),
        ({"interest_investments": "66.0001"}, "NON_COMPLIANT"),
        ({"liquid_assets": "70.001"}, "NON_COMPLIANT"),
        ({"activity": "PROHIBITED"}, "NON_COMPLIANT"),
        ({"interest_debt": None, "index_member": True}, "UNVERIFIED"),
        ({"market_value_source": None}, "UNVERIFIED"),
        (
            {
                "reviewed_on": date(2026, 1, 1),
                "period_end": date(2025, 12, 31),
                "index_as_of": date(2025, 8, 1),
            },
            "UNVERIFIED",
        ),
        ({"activity": "UNKNOWN"}, "UNVERIFIED"),
        ({"ordinary_share": False}, "UNVERIFIED"),
    ],
)
def test_sharia_strict_boundaries_and_membership_is_separate(changes, outcome):
    assert evaluate_screen(evidence(**changes), NOW.date())["status"] == outcome


def test_owner_gates_and_islamic_ranking(local_market):
    with SessionLocal() as db:
        security = db.get(EGXSecurity, "COMI")
        isin = security.isin
    client = TestClient(app, headers={"X-EGX-Gateway": KEY})
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"INTEGRATIONS_GATEWAY_SECRET": KEY}):
        anonymous = TestClient(app)
        assert anonymous.post("/api/v1/risk/settings", json={}).status_code == 403
        assert anonymous.get("/api/v1/sharia").status_code == 403
        assert (
            client.post(
                "/api/v1/risk/review", json={"source": "THNDR", "manual": {}}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/risk/settings", json={"islamic_mode": True}
            ).status_code
            == 200
        )
        try:
            with SessionLocal() as db:
                unknown = build_analysis(
                    db, db.get(EGXSecurity, "COMI"), AnalysisRequest(ticker="COMI")
                )
                assert unknown.sharia_status == "UNVERIFIED"
                assert all(r["ticker"] != "COMI" for r in opportunities(db))
            payload = evidence().model_dump(mode="json")
            result = client.post("/api/v1/sharia/COMI", json=payload)
            assert result.status_code == 200 and result.json()["status"] == "COMPLIANT"
            assert client.post("/api/v1/sharia/COMI", json=payload).status_code == 200
            assert (
                client.post(
                    "/api/v1/sharia/COMI", json={**payload, "interest_debt": "67"}
                ).status_code
                == 409
            )
            with SessionLocal() as db:
                positive = build_analysis(
                    db, db.get(EGXSecurity, "COMI"), AnalysisRequest(ticker="COMI")
                )
                assert (
                    positive.sharia_status == "COMPLIANT" and not positive.risk_blockers
                )
            client.post(
                "/api/v1/risk/settings",
                json={"islamic_mode": True, "kill_switch": True},
            ).raise_for_status()
            blocked = client.post(
                "/api/v1/ai-trading/analyze",
                json={"ticker": "COMI", "portfolio_value": 10000},
            )
            assert (
                blocked.status_code == 200
                and "KILL_SWITCH" in blocked.json()["risk_blockers"]
            )
        finally:
            with SessionLocal() as db:
                db.query(RiskSettings).delete()
                db.query(ShariaScreening).filter_by(isin=isin).delete()
                db.commit()
