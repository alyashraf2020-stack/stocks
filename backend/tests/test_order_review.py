import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.integrations.thndr_mcp import READ_TOOLS, ReadSession
from app.main import app
from app.models.notification import Notification
from app.models.order_approval import OrderApproval, ReviewChallenge
from app.models.order_event import OrderEvent
from app.models.order_proposal import OrderProposal
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import Analysis
from app.schemas.order_proposal import DraftRequest, ExactReview, TradingSettings
from app.schemas.risk import PortfolioSnapshot, RiskPolicy, RiskPosition
from app.schemas.thndr import Connection, Quote
from app.services import order_approval
from app.services import order_proposal_service as service
from app.services.order_reconciliation import capabilities
from app.services.order_validation import (
    account_limits,
    check_price,
    estimate,
    price_within_review,
)
from app.services.risk_policy import save_policy
from app.services.scanner_calendar import CAIRO
from app.services.scanner_repository import writer
from app.services.trading_readiness import readiness

KEY = "test-owner-gateway-key-only-not-production"
ISIN = "EGS60201C018"
NOW = datetime(2026, 11, 24, 16, tzinfo=CAIRO)


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'orders.db'}")
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, autoflush=False)
    with make() as db:
        db.add(
            EGXSecurity(
                ticker="COMI",
                isin=ISIN,
                arabic_name="شركة للاختبار",
                english_name="Fixture",
                sector="Banks",
                listing_status="ACTIVE",
                source_updated_at="2026-11-24",
            )
        )
        db.commit()
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", KEY)
    return make


def analysis():
    return Analysis.model_validate(
        {
            "ticker": "COMI",
            "company": "شركة للاختبار",
            "sector": "Banks",
            "freshness": "HISTORICAL",
            "provider": "Local fixture",
            "price": 100,
            "reference_session": NOW.date(),
            "signal": "BUY",
            "technical_rating": "BUY",
            "decision": "ENTER",
            "explanation_ar": "بيانات اختبار",
            "market_status": "CLOSED",
            "mean_volume": 100000,
            "levels": {
                "lower": 99,
                "upper": 101,
                "stop": 95,
                "targets": [112, 120, 130],
                "reward_to_risk": [1, 2, 3],
                "support": 96,
                "resistance": 110,
            },
        }
    )


def request(**changes):
    return DraftRequest(key=uuid4(), ticker="COMI", intent="BUY", **changes)


def draft(factory, data=None):
    with factory() as db, writer(db):
        return service.create(db, data or request(), NOW, analysis=analysis()).id


def issue(factory, key, browser="browser-a"):
    with factory() as db, writer(db):
        row = service.by_id(db, key)
        body = order_approval.issue(db, row, row.fingerprint, NOW, browser)
        return ExactReview(
            fingerprint=row.fingerprint, challenge=body["challenge"], understood=True
        )


def test_documented_tools_discovery_does_not_expand_read_allowlist():
    class Transport:
        async def list_tools(self, **kwargs):
            return SimpleNamespace(
                nextCursor=None,
                tools=[
                    SimpleNamespace(
                        name="get_orders",
                        inputSchema={"required": ["unsupported"], "properties": {}},
                    ),
                    SimpleNamespace(name="send_trade_proposal", inputSchema={}),
                    SimpleNamespace(name="get_proposal_status", inputSchema={}),
                ],
            )

        async def call_tool(self, *args, **kwargs):
            pytest.fail("The transport must not be called")

    async def examine():
        session = ReadSession(Transport())
        await session.discover()
        assert set(session.granted) == {"get_orders"}
        assert "send_trade_proposal" not in READ_TOOLS
        with pytest.raises(Exception, match="MISSING_PERMISSION"):
            await session.read("send_trade_proposal")
        with pytest.raises(Exception, match="UNSUPPORTED_TOOL_SCHEMA"):
            await session.read("get_orders")

    asyncio.run(examine())
    result = capabilities(
        Connection(
            status="CONNECTED",
            available=["send_trade_proposal", "get_orders"],
            permissions=["thndr:read"],
        )
    )
    assert result["granted_reads"] == ["get_orders"]
    assert result["proposal_grant"] == "NOT_GRANTED_IN_READ_SESSION"
    assert result["official_schema_verified"] is False


def test_readiness_fails_closed_with_read_credentials_and_no_live_feed(factory):
    connection = Connection(
        status="CONNECTED",
        permissions=["thndr:read"],
        available=["get_orders"],
        last_sync=NOW,
    )
    with factory() as db:
        row = readiness(db, NOW, connection, RiskPolicy(), https=True)
    statuses = {item.code: item.status for item in row["checks"]}
    assert row["status"] == "BLOCKED" and not row["broker_handoff"]
    assert statuses["THNDR_PROPOSAL_GRANT"] == "FAIL"
    assert (
        statuses["STRATEGY_VALIDATION"] == statuses["LICENSED_LIVE_FEED"] == "UNKNOWN"
    )
    assert statuses["OPEN_MARKET"] == "FAIL"
    assert statuses["HTTPS"] == "PASS"


@pytest.mark.parametrize(
    ("delay", "age", "isin", "session", "expected"),
    [
        ("DELAYED", 1, ISIN, "OPEN", "QUOTE_DELAYED"),
        ("REALTIME", 31, ISIN, "OPEN", "QUOTE_STALE"),
        ("REALTIME", 1, "OTHER_ID", "OPEN", "QUOTE_IDENTITY_INVALID"),
        ("REALTIME", 1, ISIN, "HALTED", "SESSION_NOT_AUTHORIZED"),
        ("REALTIME", 1, ISIN, "CLOSED", "SESSION_NOT_AUTHORIZED"),
        ("REALTIME", 1, ISIN, "OPEN", None),
    ],
)
def test_quote_gate(delay, age, isin, session, expected):
    quote = Quote(
        ticker="COMI",
        instrument_id=isin,
        exchange="EGX",
        currency="EGP",
        price=98,
        source_timestamp=NOW - timedelta(seconds=age),
        retrieved_at=NOW,
        delay_class=delay,
        provider="fixture",
        session_status="OPEN",
    )
    security = SimpleNamespace(ticker="COMI", isin=ISIN)
    market = {"live_verified": True, "session_status": session}
    assert (
        check_price(quote, security, market, NOW, TradingSettings(), {"fixture"})
        == expected
    )
    assert check_price(quote, security, market, NOW, TradingSettings()) is not None


def test_reservations_settlement_fee_and_risk_checks():
    cash = PortfolioSnapshot(
        settled_cash=1000,
        buying_power=1000,
        pending_buys=[
            {
                "ticker": "COMI",
                "reserved_cash": "800",
                "notional": "750",
                "planned_risk": "50",
            }
        ],
    )
    buy = request(shares=3)
    price = Decimal(100)
    issues = account_limits(
        buy,
        cash,
        None,
        RiskPolicy(islamic_mode=True),
        "UNVERIFIED",
        {"shares": 2},
        price,
    )
    assert {"INSUFFICIENT_CASH", "SHARIA_UNVERIFIED", "SIZE_EXCEEDS_RISK_LIMIT"} <= set(
        issues
    )
    assert "SETTLED_CASH_UNVERIFIED" in account_limits(
        buy, PortfolioSnapshot(), None, RiskPolicy(), None, None, price
    )
    assert "RESERVATIONS_UNVERIFIED" in account_limits(
        buy, PortfolioSnapshot(), None, RiskPolicy(), None, None, price
    )
    sell = DraftRequest(key=uuid4(), ticker="COMI", intent="FULL_EXIT", shares=3)
    pos = RiskPosition(ticker="COMI", shares=3, sellable_shares=2)
    assert account_limits(sell, cash, pos, RiskPolicy(), None, None, price) == [
        "INSUFFICIENT_SELLABLE_SHARES"
    ]
    assert estimate(RiskPolicy(), "BUY", price, 2)["required_cash"] is None
    costs = estimate(
        RiskPolicy(commission_rate=".01", buy_tax_rate=".02", sell_tax_rate="0"),
        "BUY",
        price,
        2,
    )
    assert costs["required_cash"] == Decimal(206)
    config = TradingSettings(max_adverse_move_bps=25)
    assert price_within_review("BUY", Decimal(100), Decimal("100.25"), config)
    assert not price_within_review("SELL", Decimal(100), Decimal("99.74"), config)


def test_immutable_dedup_and_no_broker_execution(factory):
    first = request()
    key = draft(factory, first)
    assert draft(factory, first) == key
    with pytest.raises(service.ProposalError, match="DUPLICATE_ACTIVE_INTENT"):
        draft(factory, request())
    with pytest.raises(service.ProposalError, match="IDEMPOTENCY_KEY_CONFLICT"):
        draft(factory, first.model_copy(update={"shares": 90}))
    with factory() as db:
        value = service.view(service.by_id(db, key))
        assert not value["executable"] and not value["handoff_enabled"]
        assert value["broker"]["execution_status"] == "UNKNOWN"
        assert value["broker"]["broker_reference"] is None
        assert value["shares"] is None and value["costs"]["commission"] is None


def test_owner_fingerprint_browser_and_concurrency(factory):
    key = draft(factory)
    payload = issue(factory, key)
    with (
        pytest.raises(service.ProposalError, match="REVIEW_BINDING_MISMATCH"),
        factory() as db,
        writer(db),
    ):
        order_approval.confirm(db, service.by_id(db, key), payload, NOW, "browser-b")
    with (
        pytest.raises(service.ProposalError, match="REVIEW_BINDING_MISMATCH"),
        factory() as db,
        writer(db),
    ):
        order_approval.confirm(
            db,
            service.by_id(db, key),
            payload.model_copy(update={"fingerprint": "f" * 64}),
            NOW,
            "browser-a",
        )

    def attempt(_):
        with factory() as db, writer(db):
            return order_approval.confirm(
                db, service.by_id(db, key), payload, NOW, "browser-a"
            )

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(attempt, range(5)))
    assert outcomes.count(None) == 1
    assert outcomes.count("REVIEW_NO_LONGER_AVAILABLE") == 4
    with factory() as db:
        recorded = db.get(OrderApproval, key)
        assert (
            recorded.purpose == "LOCAL_REVIEW_ONLY"
            and recorded.challenge_hash != payload.challenge
        )
        assert db.get(ReviewChallenge, key) is None
        assert [
            x.kind for x in db.scalars(select(OrderEvent).order_by(OrderEvent.id))
        ] == [
            "DRAFT",
            "BLOCKED",
            "APPROVAL_REQUIRED",
            "LOCAL_REVIEWED",
        ]


def test_expiry_and_policy_round_trip(factory):
    key = draft(factory)
    payload = issue(factory, key)
    with factory() as db, writer(db):
        row = service.by_id(db, key)
        assert (
            order_approval.confirm(
                db, row, payload, NOW + timedelta(seconds=121), "browser-a"
            )
            == "REVIEW_CHALLENGE_EXPIRED"
        )
    with factory() as db:
        save_policy(db, RiskPolicy(advanced_enabled=True))
        save_policy(db, RiskPolicy())
    with factory() as db, writer(db):
        row = service.by_id(db, key)
        assert (
            order_approval.confirm(db, row, payload, NOW, "browser-a")
            == "REVIEW_NO_LONGER_AVAILABLE"
        )
        assert row.state == "INVALIDATED"


def test_price_change_invalidates_exact_review_and_preserves_history(
    factory, monkeypatch
):
    from app.services import market_import

    key = draft(factory)
    payload = issue(factory, key)
    monkeypatch.setattr(
        market_import, "approved_series", lambda *_: (None, [{"close": 101}])
    )
    with factory() as db, writer(db):
        old = service.by_id(db, key)
        assert (
            order_approval.confirm(db, old, payload, NOW, "browser-a")
            == "REVIEW_NO_LONGER_AVAILABLE"
        )
        assert old.state == "INVALIDATED"
        refreshed = service.create(
            db,
            request(),
            NOW,
            parent=old,
            analysis=analysis().model_copy(update={"price": 101}),
        )
        assert (
            refreshed.id != key
            and refreshed.parent_id == key
            and refreshed.version == 2
        )
        assert old.data["reference"] == "100.000000"
        assert refreshed.data["reference"] == "101.000000"
        assert refreshed.fingerprint != old.fingerprint
        assert db.get(OrderApproval, key) is None


def test_emergency_stop_invalidates_buy_challenge_and_preserves_exit(factory):
    key = draft(factory)
    issue(factory, key)
    exit_key = draft(
        factory, DraftRequest(key=uuid4(), ticker="COMI", intent="STOP_REVIEW")
    )
    with factory() as db:
        save_policy(db, RiskPolicy(kill_switch=True))
        assert db.get(OrderProposal, key).state == "INVALIDATED"
        assert db.get(OrderProposal, exit_key).state == "BLOCKED"
        assert db.get(ReviewChallenge, key) is None


def test_scanner_opt_in_and_unchanged_signal_never_duplicates(factory):
    row = {
        "ticker": "COMI",
        "category": "BUY_REVIEW",
        "analysis": analysis().model_dump(mode="json"),
    }
    job = SimpleNamespace(mode="WATCHLIST", session=NOW.date().isoformat())
    with factory() as db, writer(db):
        service.from_scan(db, job, [("same", row, False)], NOW)
        assert db.scalar(select(func.count()).select_from(OrderProposal)) == 0
        service.set_settings(
            db, TradingSettings(mode="SEMI_AUTOMATIC_REVIEW", automatic_drafts=True)
        )
    with factory() as db, writer(db):
        service.from_scan(db, job, [("same", row, False)], NOW)
        service.from_scan(db, job, [("same", row, False)], NOW)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(OrderProposal)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        proposal = db.scalar(select(OrderProposal))
        assert proposal.data["origin"] == "SCANNER" and not proposal.data["executable"]


def test_https_endpoints_no_write_acknowledge_isolation(factory, monkeypatch):
    from app.api.v1.endpoints import order_proposals
    from app.schemas.thndr import Portfolio

    monkeypatch.setattr(order_proposals, "datetime", SimpleNamespace(now=lambda _: NOW))
    monkeypatch.setattr(service, "build_analysis", lambda *args, **kwargs: analysis())

    async def unavailable():
        return Portfolio()

    monkeypatch.setattr(order_proposals, "portfolio", unavailable)

    def provider():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = provider
    try:
        client = TestClient(
            app, base_url="https://example.test", headers={"X-EGX-Gateway": KEY}
        )
        path = "/api/v1/orders/proposals"
        assert TestClient(app).get(path).status_code == 403
        created = client.post(path, json=request().model_dump(mode="json")).json()
        route = path + "/" + created["id"]
        assert client.post(route + "/handoff").status_code == 409
        review = client.post(
            route + "/review", json={"fingerprint": created["fingerprint"]}
        )
        assert review.status_code == 200 and "HttpOnly" in review.headers["set-cookie"]
        with factory() as db, writer(db):
            alert = db.scalar(
                select(Notification).where(Notification.category == "DRAFT_REVIEW")
            )
            assert alert is not None
            alert_id = alert.id
            alert.expires = (
                4102444800  # Keep this fixed fixture independent of the wall clock.
            )
        acknowledged = client.post(
            f"/api/v1/notifications/{alert_id}", json={"acknowledge": True}
        )
        assert acknowledged.status_code == 200
        with factory() as db:
            assert db.get(Notification, alert_id).acknowledged_at is not None
            assert db.get(OrderProposal, created["id"]).state == "APPROVAL_REQUIRED"
            assert db.get(OrderApproval, created["id"]) is None
        payload = {
            "fingerprint": created["fingerprint"],
            "challenge": review.json()["challenge"],
            "understood": True,
        }
        assert (
            client.post(route + "/confirm-local", json=payload).json()["state"]
            == "LOCAL_REVIEWED"
        )
        assert client.post(route + "/confirm-local", json=payload).status_code == 409
        assert client.post(route + "/handoff").status_code == 409
        assert (
            client.post(
                path, json=request(source="THNDR").model_dump(mode="json")
            ).status_code
            == 409
        )
        assert (
            client.post(
                path, json={**request().model_dump(mode="json"), "source": "PAPER"}
            ).status_code
            == 422
        )
    finally:
        app.dependency_overrides.pop(get_db)
