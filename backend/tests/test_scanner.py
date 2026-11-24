import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models.market_scan import MarketScan
from app.models.notification import Notification
from app.models.notification_outbox import NotificationOutbox
from app.models.scheduled_job import ScheduledJob
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import Analysis, PlanLevels
from app.schemas.risk import PortfolioSnapshot, RiskPolicy, RiskPosition
from app.schemas.scanner import ENV, ScannerEnvironment, ScannerSettings
from app.services import market_scanner
from app.services.alert_engine import symbol_alerts
from app.services.notification_service import RetryDelivery, deliver_one, emit
from app.services.risk_policy import save_policy
from app.services.scanner_calendar import CAIRO, SPECIAL, calendar_at
from app.services.scanner_health import health
from app.services.scanner_repository import (
    claim,
    enqueue,
    fail,
    heartbeat,
    load_settings,
    publish,
    renew,
    save_settings,
    writer,
)
from app.workers.trading_scheduler import tick
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 11, 23, 16, tzinfo=CAIRO)
KEY = "scanner-test-gateway-" * 3


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scanner.db'}")
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, autoflush=False)
    yield make
    engine.dispose()


def config(sessions, **kwargs):
    with sessions() as db:
        current = load_settings(db)
        db.rollback()
        return save_settings(db, current.model_copy(update=kwargs))


def seed(sessions):
    with sessions() as db:
        db.add(
            EGXSecurity(
                ticker="COMI",
                isin="EGS60201C018",
                arabic_name="البنك التجاري",
                english_name="Commercial Bank",
                sector="Banks",
                listing_status="ACTIVE",
                source_updated_at="2026-11-20",
            )
        )
        db.commit()


def job_for(sessions, *, manual=False, now=NOW):
    with sessions() as db:
        return enqueue(db, calendar_at(now), now.timestamp(), manual=manual)


def claimed(sessions, now=NOW):
    with sessions() as db:
        return claim(db, now.timestamp())


def opportunity(now=NOW):
    report = Analysis(
        ticker="COMI",
        company="البنك التجاري",
        sector="Banks",
        signal="BUY",
        decision="BUY",
        explanation_ar="داخل النطاق",
        price=11,
        provider="FIXTURE",
        price_timestamp=now,
        reference_session=now.date(),
        freshness="HISTORICAL",
        market_status="CLOSED",
        technical_rating="BUY",
        score=70,
        sharia_status="UNVERIFIED",
        levels=PlanLevels(
            lower=10,
            upper=12,
            stop=8,
            targets=(15, 16, 17),
            reward_to_risk=(1.5, 2.5, 3.5),
            support=9,
            resistance=14,
        ),
    )
    return {
        "ticker": report.ticker,
        "category": "BUY_REVIEW",
        "rank": 30,
        "reason": None,
        "qualified": False,
        "executable": False,
        "analysis": report.model_dump(mode="json"),
        "observation": {
            "freshness": "HISTORICAL",
            "source_timestamp": now.isoformat(),
            "validation_status": "VALID",
            "instrument_id": "EGS60201C018",
        },
        "flags": {},
    }


@pytest.mark.parametrize(
    ("hour", "minute", "scheduled", "actual"),
    [
        (9, 30, "PRE_MARKET", "PRE_MARKET"),
        (10, 0, "OPEN", "UNKNOWN"),
        (14, 29, "OPEN", "UNKNOWN"),
        (14, 30, "CLOSED", "CLOSED"),
    ],
)
def test_cairo_calendar_boundary(hour, minute, scheduled, actual):
    clock = datetime(2026, 7, 20, hour, minute, tzinfo=CAIRO)
    data = calendar_at(clock.astimezone(UTC))
    assert (data["scheduled_status"], data["session_status"]) == (scheduled, actual)
    assert data["live_verified"] is False
    assert data["completed_session"] == (
        "2026-07-20" if actual == "CLOSED" else "2026-07-19"
    )


def test_calendar_holidays_ramadan_halt_and_out_of_coverage(monkeypatch):
    assert (
        calendar_at(datetime(2026, 3, 18, 13, 30, tzinfo=CAIRO))["completed_session"]
        == "2026-03-18"
    )
    assert (
        calendar_at(datetime(2026, 3, 23, 15, tzinfo=CAIRO))["completed_session"]
        == "2026-03-18"
    )
    assert (
        calendar_at(datetime(2026, 5, 31, 15, tzinfo=CAIRO))["completed_session"]
        == "2026-05-25"
    )
    assert (
        calendar_at(datetime(2027, 1, 3, 13, tzinfo=CAIRO))["completed_session"] is None
    )
    monkeypatch.setitem(SPECIAL, NOW.date(), "HALTED")
    assert calendar_at(NOW)["session_status"] == "HALTED"
    monkeypatch.setitem(SPECIAL, NOW.date(), (time(10), time(15)))
    assert calendar_at(NOW.replace(hour=14))["completed_session"] == "2026-11-22"


def test_settings_and_schedule(sessions, monkeypatch):
    monkeypatch.setenv("SCANNER_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    assert ScannerEnvironment().SCANNER_INTERVAL_SECONDS == 300
    assert tick(sessions, NOW.timestamp()) is None
    settings = config(sessions, enabled=True)
    assert settings.revision == 1
    assert tick(sessions, NOW.replace(hour=14, minute=40).timestamp()) is None
    first = tick(sessions, NOW.timestamp())
    assert first is not None
    assert tick(sessions, NOW.timestamp() + 60) == first
    assert job_for(sessions, manual=True) == first
    with sessions() as db:
        assert save_settings(db, ScannerSettings()) is None
    config(sessions, enabled=False)
    assert claimed(sessions) is None
    with sessions() as db:
        assert db.get(ScheduledJob, first).status == "CANCELLED"


def test_multiple_workers_recover_fenced_lease_and_heartbeat(sessions):
    config(sessions, enabled=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert len(set(pool.map(lambda _: job_for(sessions), range(6)))) == 1
        claims = list(pool.map(lambda _: claimed(sessions), range(6)))
    assert sum(c is not None for c in claims) == 1
    job, old = next(c for c in claims if c)
    with sessions() as db:
        heartbeat(db, "first", NOW.timestamp(), job)
    with sessions() as db:
        assert health(db, NOW.timestamp() + 2, calendar_at(NOW))["worker_online"]
        assert not health(db, NOW.timestamp() + 20, calendar_at(NOW))["worker_online"]
    later = NOW + timedelta(seconds=ENV.SCANNER_LEASE_SECONDS + 1)
    recovered, new = claimed(sessions, later)
    assert recovered == job and new != old
    with sessions() as db:
        assert not renew(db, job, old, later.timestamp())
        assert not publish(db, job, old, later.timestamp(), {"rows": []})
        assert publish(db, job, new, later.timestamp(), {"rows": []})
    with sessions() as db:
        assert db.get(ScheduledJob, job).attempts == 2
        assert db.get(MarketScan, job).summary["scanned"] == 0


def test_retry_backoff_and_exhaustion(sessions):
    job = job_for(sessions, manual=True)
    clock = NOW
    for step in range(3):
        _, token = claimed(sessions, clock)
        with sessions() as db:
            assert fail(db, job, token, clock.timestamp(), "JOB_TIMEOUT")
        assert claimed(sessions, clock) is None
        clock += timedelta(seconds=31)
    with sessions() as db:
        assert db.get(ScheduledJob, job).status == "FAILED"
        assert db.scalar(select(Notification)).category == "SCANNER_FAILURE"


@pytest.mark.parametrize(
    ("updated", "code"),
    [
        (RiskPolicy(kill_switch=True), "KILL_SWITCH"),
        (RiskPolicy(islamic_mode=True), "SHARIA_UNVERIFIED"),
        (RiskPolicy(max_stock_allocation="0.10"), "POLICY_CHANGED"),
    ],
)
def test_publication_rechecks_policy_and_never_publishes_entry_alert(
    sessions, updated, code
):
    seed(sessions)
    job = job_for(sessions, manual=True)
    _, token = claimed(sessions)
    with sessions() as db:
        save_policy(db, updated)
    with sessions() as db:
        assert publish(
            db,
            job,
            token,
            NOW.timestamp(),
            {
                "policy": RiskPolicy().model_dump(mode="json"),
                "rows": [("a", opportunity(), False)],
            },
        )
    with sessions() as db:
        row = db.get(MarketScan, job).results[0]
        assert not row["executable"] and not row["qualified"]
        assert code in row["analysis"]["risk_blockers"]
        assert row["analysis"]["signal"] == "WAIT"
        assert all(n.category != "BUY_REVIEW" for n in db.scalars(select(Notification)))


def test_symbol_isolation_snapshot_reuse_and_watchlist_priority(sessions, monkeypatch):
    seed(sessions)
    config(sessions, watchlist=["COMI", "SWDY", "FAIL"])
    monkeypatch.setattr(ENV, "SCANNER_MAX_SYMBOLS_PER_SCAN", 5)
    calls = []

    def fake_analysis(db, security, request, **kwargs):
        calls.append(security.ticker)
        return Analysis.model_validate(opportunity()["analysis"])

    monkeypatch.setattr(market_scanner, "build_analysis", fake_analysis)
    job_id = job_for(sessions, manual=True)
    _, token = claimed(sessions)
    data = market_scanner.collect(
        sessions, {"revision": 1, "session": "2026-11-23"}, NOW
    )
    assert [item[1]["ticker"] for item in data["rows"]] == ["COMI", "SWDY", "FAIL"]
    assert data["rows"][1][1]["category"] == "UNAVAILABLE"
    assert calls == ["COMI"]
    with sessions() as db:
        assert publish(db, job_id, token, NOW.timestamp(), data)
    data = market_scanner.collect(
        sessions, {"revision": 1, "session": "2026-11-23"}, NOW
    )
    assert data["rows"][0][2] is True
    assert calls == ["COMI"]


def test_thndr_gateway_failure_rate_bound_and_no_manual_fallback(sessions, monkeypatch):
    config(sessions, mode="THNDR_PORTFOLIO", manual=PortfolioSnapshot(positions=[]))
    calls = []

    async def offline():
        from fastapi import HTTPException

        calls.append("access")
        raise HTTPException(503, "provider secret")

    monkeypatch.setattr(market_scanner, "portfolio", offline)
    job = {"revision": 1, "session": "2026-11-23"}
    assert market_scanner.collect(sessions, job, NOW) == {
        "rows": [],
        "error": "THNDR_UNAVAILABLE",
    }
    assert market_scanner.collect(sessions, job, NOW) == {
        "rows": [],
        "error": "THNDR_RATE_LIMITED",
    }
    assert calls == ["access"]


def test_delayed_and_stale_thresholds(sessions):
    report = Analysis.model_validate(opportunity()["analysis"])
    pos = RiskPosition(ticker="COMI", stop="12")
    checked = {"validation_status": "VALID"}
    report.freshness = "DELAYED"
    assert market_scanner.interactions(report, pos, checked)["stop"] == "12"
    report.freshness = "STALE"
    assert market_scanner.interactions(report, pos, checked) == {}
    report.freshness, report.price = "HISTORICAL", 16
    assert market_scanner.interactions(report, pos, checked)["target"] == 2
    assert (
        market_scanner.interactions(report, pos, {"validation_status": "INVALID"}) == {}
    )


def test_alert_transition_dedupe_and_outbox_retry(sessions):
    settings = ScannerSettings()
    current = opportunity()
    current["flags"] = {"stop": "12", "target": 2}
    current["threshold_observation"] = "BROKER"
    current["broker_observation"] = {**current["observation"], "freshness": "DELAYED"}
    epoch = NOW.timestamp()
    with sessions() as db, writer(db):
        symbol_alerts(db, settings, epoch, current, {}, "snapshot")
        symbol_alerts(db, settings, epoch + 1, current, current, "second")
        symbol_alerts(db, settings, epoch + 3, current, {}, "snapshot")
    with sessions() as db, writer(db):
        notes = list(db.scalars(select(Notification)))
        assert {n.category for n in notes} == {"BUY_REVIEW", "STOP", "TARGET"}
        stop = next(n for n in notes if n.category == "STOP")
        assert (
            stop.payload["freshness"] == "DELAYED"
            and stop.payload["executable"] is False
        )
        db.get(NotificationOutbox, stop.id).status = "PENDING"
        key = stop.id
    calls = []

    class TestAdapter:
        def deliver(self, notification_id, facts):
            calls.append((notification_id, facts))
            if len(calls) == 1:
                raise RetryDelivery(60)

    adapter = TestAdapter()
    assert deliver_one(sessions, adapter, lambda: epoch)
    assert not deliver_one(sessions, adapter, lambda: epoch + 59)
    assert deliver_one(sessions, adapter, lambda: epoch + 60)
    assert calls == [(key, {"category": "STOP"})] * 2
    with sessions() as db:
        outbox = db.get(NotificationOutbox, key)
        assert outbox.status == "DELIVERED"
        assert [record["result"] for record in outbox.history] == ["RETRY", "DELIVERED"]


def test_outbox_rollback_and_preference(sessions):
    with pytest.raises(ValueError), sessions() as db, writer(db):
        emit(
            db,
            ScannerSettings(),
            NOW.timestamp(),
            "BUY_REVIEW",
            "OPPORTUNITY",
            {"ticker": "COMI"},
            "once",
        )
        raise ValueError("abort publication")
    with sessions() as db, writer(db):
        assert list(db.scalars(select(Notification))) == []
        assert list(db.scalars(select(NotificationOutbox))) == []
        settings = ScannerSettings(
            muted_categories=["BUY_REVIEW"], minimum_severity="WARNING"
        )
        emit(db, settings, NOW.timestamp(), "BUY_REVIEW", "OPPORTUNITY", {}, "muted")
        emit(db, settings, NOW.timestamp(), "KILL_SWITCH", "CRITICAL", {}, "still-on")
        assert [n.category for n in db.scalars(select(Notification))] == ["KILL_SWITCH"]


def test_owner_endpoints_and_secret_redaction(sessions, monkeypatch):
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-in-json")
    monkeypatch.setenv("THNDR_ENCRYPTION_KEY", "must-not-be-in-json")

    def db_override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    try:
        client = TestClient(app)
        for path in (
            "scanner/settings",
            "scanner/status",
            "scanner/history",
            "scanner/results",
            "notifications",
        ):
            assert client.get(f"/api/v1/{path}").status_code == 403
        assert client.post("/api/v1/scanner/run", json={}).status_code == 403
        assert client.post("/api/v1/scanner/settings", json={}).status_code == 403
        headers = {"X-EGX-Gateway": KEY}
        response = client.get("/api/v1/scanner/settings", headers=headers)
        assert (
            response.status_code == 200
            and "no-store" in response.headers["cache-control"]
        )
        assert KEY not in response.text and "must-not-be-in-json" not in response.text
        assert (
            client.post(
                "/api/v1/scanner/settings",
                headers=headers,
                json={
                    **response.json(),
                    "enabled": True,
                    "interval_seconds": 60,
                },
            ).status_code
            == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_scanner_schema_adds_storage_without_touching_candles(sessions):
    with sessions() as db:
        path = db.get_bind().url.database
    with sqlite3.connect(path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    assert {
        "egx_candles",
        "scanner_jobs",
        "scanner_runs",
        "scanner_notifications",
        "scanner_notification_outbox",
    } <= names


def test_scanner_reuses_budget_and_skips_ai_for_unchanged_snapshots(
    sessions, tmp_path, monkeypatch
):
    from app.services import ai_decision_engine

    seed(sessions)
    config(sessions, watchlist=["COMI"])
    calls = []
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-no-real-requests")
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", KEY)
    monkeypatch.setenv("AI_LEDGER_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("AI_DAILY_BUDGET_USD", "0")
    monkeypatch.setattr(ENV, "SCANNER_AI_ENABLED", True)
    monkeypatch.setattr(
        market_scanner,
        "build_analysis",
        lambda *args, **kwargs: Analysis.model_validate(opportunity()["analysis"]),
    )
    monkeypatch.setattr(
        ai_decision_engine, "interpret", lambda *args: calls.append("network")
    )
    job = job_for(sessions, manual=True)
    _, token = claimed(sessions)
    data = market_scanner.collect(
        sessions, {"revision": 1, "session": "2026-11-23"}, NOW
    )
    assert data["rows"][0][1]["analysis"]["ai_status"] == "BUDGET_EXHAUSTED"
    with sessions() as db:
        assert publish(db, job, token, NOW.timestamp(), data)
    data = market_scanner.collect(
        sessions, {"revision": 1, "session": "2026-11-23"}, NOW
    )
    assert data["rows"][0][2] is True
    assert calls == []


def test_authorized_thndr_observation_keeps_eod_and_delayed_quote_separate(
    sessions, monkeypatch
):
    from app.schemas.thndr import CheckedQuote, Holding, Portfolio

    seed(sessions)
    config(sessions, mode="THNDR_PORTFOLIO")
    retrieved = NOW - timedelta(seconds=10)
    quote = CheckedQuote(
        ticker="COMI",
        instrument_id="EGS60201C018",
        exchange="EGX",
        currency="EGP",
        price=9.0,
        source_timestamp=NOW - timedelta(minutes=15),
        retrieved_at=retrieved,
        provider="THNDR",
        delay_class="DELAYED",
        session_status="UNKNOWN",
        freshness="DELAYED",
        validation_status="VALID",
        eligible_for_proposal=False,
    )

    async def authorized():
        return Portfolio(
            last_sync=retrieved,
            holdings=[
                Holding(
                    ticker="COMI",
                    instrument_id=quote.instrument_id,
                    quantity=5,
                    average_price=10,
                    quote=quote,
                )
            ],
        )

    monkeypatch.setattr(market_scanner, "portfolio", authorized)

    def analyze(db, security, request, brokerage=None, **kwargs):
        report = Analysis.model_validate(opportunity()["analysis"])
        if brokerage:
            report.price = quote.price
            report.price_timestamp = quote.source_timestamp
            report.freshness = "DELAYED"
        else:
            report.price_timestamp = None
        return report

    monkeypatch.setattr(market_scanner, "build_analysis", analyze)
    data = market_scanner.collect(
        sessions, {"revision": 1, "session": "2026-11-23"}, NOW
    )
    row = data["rows"][0][1]
    assert row["observation"]["freshness"] == "HISTORICAL"
    assert row["observation"]["time_basis"] == "SESSION_CLOSE"
    delayed = row["broker_observation"]
    assert delayed["freshness"] == "DELAYED"
    assert delayed["retrieval_timestamp"] == retrieved.isoformat()
    assert row["qualified"] is False and row["executable"] is False
