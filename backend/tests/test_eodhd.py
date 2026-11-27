from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Event
from urllib.error import HTTPError

import pytest
import time_machine
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.backtest_run import SimulationDataset
from app.models.eodhd import EodhdCandle, EodhdConfig, EodhdUsage
from app.models.security import EGXSecurity
from app.schemas.scanner import ScannerSettings
from app.services import eodhd as service
from app.services.data_provider.eodhd import EodhdProvider, ProviderError
from app.services.data_provider.manager import default_provider_manager
from app.services.market_import import readiness
from app.services.scanner_calendar import hours
from app.services.scanner_repository import save_settings

NOW = datetime(2026, 11, 27, 14, tzinfo=UTC)
SESSION = date(2026, 11, 26)
TOKEN = "fixture-only-token-123"
KEY = "test-only-gateway-value-thirty-two-characters"
SETTINGS = {"enabled": True, "automatic": True, "retry": False, "exclusive": True}


def equity(ticker, isin):
    return EGXSecurity(
        ticker=ticker,
        isin=isin,
        english_name=ticker,
        arabic_name=ticker,
        sector="Industrials",
        listing_status="ACTIVE",
        source_updated_at="2026",
    )


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'private.db'}")
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setenv("NOTIFICATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("EODHD_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", KEY)
    with make() as db:
        db.add(equity("SWDY", service.BOOTSTRAP["SWDY"]))
        db.commit()
        service.configure(db, SETTINGS, TOKEN)
    yield make
    engine.dispose()


def bar(day, close=100):
    return {
        "date": day.isoformat(),
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 10000,
        "adjusted_close": 11,
    }


def sample():
    days = [SESSION - timedelta(days=i) for i in range(110)]
    return [bar(day) for day in reversed(days) if isinstance(hours(day), tuple)]


class FixtureProvider:
    def __init__(self, used=0, error=None):
        self.used, self.error = used, error
        self.calls = []

    def usage(self, token, day):
        assert token == TOKEN
        self.calls.append("usage")
        return self.used

    def history(self, token, ticker, start, end):
        assert token == TOKEN and ticker == "SWDY"
        self.calls.append(("history", start, end))
        if self.error:
            raise ProviderError(self.error)
        return sample()

    def catalog(self, token):
        assert token == TOKEN
        self.calls.append("catalog")
        return dict(service.BOOTSTRAP)


def sync(db, upstream, **options):
    return service.network(
        db,
        "history",
        ticker="SWDY",
        provider=upstream,
        **({"clock": lambda: NOW} | options),
    )


def test_quota_is_atomic_and_resets_by_utc_date(factory):
    def spend(_):
        with factory() as db:
            return service.reserve(db, NOW, 0, charge=True)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(spend, range(36))) == 20
    with factory() as db:
        assert service.reserve(db, NOW + timedelta(days=1), 0, charge=True)
        assert db.get(EodhdUsage, "2026-11-27").reserved == 20
        assert db.get(EodhdUsage, "2026-11-28").reserved == 1


def test_account_usage_and_failed_data_call_protect_bonus(factory):
    upstream = FixtureProvider(used=19, error="SYMBOL_UNAVAILABLE")
    with factory() as db:
        assert sync(db, upstream) == {"status": "SYMBOL_UNAVAILABLE"}
        with pytest.raises(ProviderError, match="FREE_QUOTA_EXHAUSTED"):
            service.network(db, "catalog", provider=upstream, clock=lambda: NOW)
        data = service.status(db, NOW)
        assert (data["projected"], data["reserved"], data["remaining"]) == (20, 1, 0)
    assert len([call for call in upstream.calls if call != "usage"]) == 1


def test_usage_contract_previous_day_and_bonus(monkeypatch):
    provider = EodhdProvider()
    response = {
        "apiRequests": "20",
        "dailyRateLimit": "20",
        "apiRequestsDate": "2026-11-26",
        "extraLimit": "500",
        "email": "fixture@example.test",
    }
    monkeypatch.setattr(provider, "_fetch", lambda *args: response)
    assert provider.usage(TOKEN, NOW.date()) == 0
    assert provider.usage(TOKEN, SESSION) == 20
    response["dailyRateLimit"] = 100000
    with pytest.raises(ProviderError, match="FREE_PLAN_UNVERIFIED"):
        provider.usage(TOKEN, NOW.date())
    response.update(dailyRateLimit=20, apiRequests=True)
    with pytest.raises(ProviderError, match="USAGE_UNVERIFIED"):
        provider.usage(TOKEN, NOW.date())


def test_missing_usage_blocks_market_request(factory):
    class Unverified(FixtureProvider):
        def usage(self, token, day):
            raise ProviderError("USAGE_UNVERIFIED")

    provider = Unverified()
    with factory() as db:
        with pytest.raises(ProviderError, match="USAGE_UNVERIFIED"):
            sync(db, provider)
        assert service.status(db, NOW)["reserved"] == 0
    assert not provider.calls


def test_simultaneous_market_requests_share_account_lock(factory):
    entered, release = Event(), Event()

    class Slow(FixtureProvider):
        def usage(self, token, day):
            entered.set()
            assert release.wait(5)
            return 0

    upstream = Slow()

    def first():
        with factory() as db:
            return service.network(db, "catalog", provider=upstream, clock=lambda: NOW)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert entered.wait(3)
            with factory() as db:
                with pytest.raises(ProviderError, match="SYNC_BUSY"):
                    sync(db, upstream)
        finally:
            release.set()
        assert future.result()["status"] == "CATALOG_READY"
    assert upstream.calls == ["catalog"]


def test_valid_eod_is_deduplicated_and_only_analysis_qualified(factory):
    upstream = FixtureProvider()
    with factory() as db, time_machine.travel(NOW, tick=False):
        assert sync(db, upstream) == {"status": "VALIDATED_EOD", "added": len(sample())}
        assert sync(db, upstream)["added"] == 0
        assert db.scalar(select(func.count()).select_from(EodhdCandle)) == len(sample())
        assert db.scalar(select(func.count()).select_from(SimulationDataset)) == 0
        analysis = default_provider_manager.get_analytical_bars(
            "SWDY", db=db, allow_network=False, completed_session=SESSION
        )
        assert analysis["current_analysis_eligible"]
        assert analysis["bars"][-1]["close"] == 100
        assert analysis["actual_provider"] == "EODHD"
        assert analysis["bars"][-1]["retrieved_at"]
        summary = readiness(db, NOW)
        stock = next(item for item in summary["items"] if item["ticker"] == "SWDY")
        assert (
            stock["analysis"]
            and not stock["paper_dataset"]
            and not stock["backtest_dataset"]
        )
        later = default_provider_manager.get_analytical_bars(
            "SWDY",
            db=db,
            allow_network=False,
            completed_session=SESSION + timedelta(days=3),
        )
        assert not later["current_analysis_eligible"] and later["sessions_behind"] == 1


def test_invalid_bars_and_ambiguous_mapping_are_rejected(factory):
    raw = [
        bar(SESSION),
        bar(SESSION, close=105),
        bar(SESSION + timedelta(days=3)),
        bar(SESSION - timedelta(days=1)) | {"volume": True},
        bar(SESSION - timedelta(days=2)) | {"open": 500},
    ]
    assert (
        service.verified_rows(raw, SESSION - timedelta(days=5), SESSION, "SWDY") == []
    )
    with factory() as db:
        db.get(EodhdConfig, 1).catalog = {"SWDY": "EGS000000001"}
        db.commit()
        provider = FixtureProvider()
        with pytest.raises(ProviderError, match="SYMBOL_MAPPING_UNVERIFIED"):
            sync(db, provider)
        assert not provider.calls


def test_priority_and_retry_controls(factory, monkeypatch):
    with factory() as db:
        catalog = dict(service.BOOTSTRAP)
        for n, ticker in enumerate(("COMI", "AMOC", "TEST"), start=1):
            catalog[ticker] = f"EGS00000000{n}"
            db.add(equity(ticker, catalog[ticker]))
        db.get(EodhdConfig, 1).catalog = catalog
        db.commit()
        save_settings(db, ScannerSettings(watchlist=["SWDY"]))
        monkeypatch.setattr(
            service,
            "status_for",
            lambda _db, sec, _day: {
                "status": "COMPLIANT" if sec.ticker == "AMOC" else "UNVERIFIED",
            },
        )
        assert service.priority(db, NOW, {"COMI": catalog["COMI"]}) == [
            "COMI",
            "SWDY",
            "AMOC",
            "TEST",
        ]
        db.rollback()
        upstream = FixtureProvider(error="UPSTREAM_UNAVAILABLE")
        assert sync(db, upstream)["status"] == "UPSTREAM_UNAVAILABLE"
        during = NOW + timedelta(minutes=20)
        with pytest.raises(ProviderError, match="RETRY_COOLDOWN"):
            sync(db, upstream, auto=True, clock=lambda: during)
        db.rollback()
        after = NOW + timedelta(minutes=31)
        with pytest.raises(ProviderError, match="RETRY_PAUSED"):
            sync(db, upstream, auto=True, clock=lambda: after)
        db.rollback()
        service.configure(db, SETTINGS | {"retry": True}, None)
        assert (
            sync(db, upstream, auto=True, clock=lambda: after)["status"]
            == "UPSTREAM_UNAVAILABLE"
        )


def test_owner_api_encrypts_token_and_sanitizes_bad_inputs(factory):
    def provide_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = provide_db
    try:
        with TestClient(app, base_url="https://owner.example.test") as client:
            path = "/api/v1/data/eodhd"
            assert client.get(path).status_code == 403
            headers = {"X-EGX-Gateway": KEY}
            marker = "secret-value-must-not-appear"
            invalid = client.post(
                path + "/settings", json={"token": marker}, headers=headers
            )
            assert invalid.status_code == 422 and marker not in invalid.text
            saved = client.post(
                path + "/settings", json=SETTINGS | {"token": marker}, headers=headers
            )
            assert (
                saved.status_code == 200
                and saved.json()["configured"]
                and marker not in saved.text
            )
            assert saved.headers["cache-control"] == "private, no-store"
            with factory() as db:
                encrypted = db.get(EodhdConfig, 1).encrypted_token
                assert marker not in encrypted
                assert service.cipher().decrypt(encrypted.encode()).decode() == marker
            assert (
                client.post(path + "/disconnect", json={}, headers=headers).json()[
                    "configured"
                ]
                is False
            )
    finally:
        app.dependency_overrides.pop(get_db)


def test_provider_error_does_not_leak_url_or_token(monkeypatch, caplog):
    provider = EodhdProvider()

    def fail(request, **kwargs):
        assert request.host == "eodhd.com"
        assert request.full_url.split("?")[0].endswith("/SWDY.EGX")
        raise HTTPError(request.full_url, 403, TOKEN, None, None)

    monkeypatch.setattr(provider.opener, "open", fail)
    with pytest.raises(ProviderError, match="^ACCESS_DENIED$") as error:
        provider.history(TOKEN, "SWDY", SESSION, SESSION)
    assert TOKEN not in str(error.value) + caplog.text


def test_incremental_refresh_counts_only_missing_rows_and_wakes_scanner(factory):
    from app.services.market_import import scan_window

    upcoming = SESSION + timedelta(days=3)
    timestamp = datetime(2026, 11, 29, 14, tzinfo=UTC)

    class Incremental(FixtureProvider):
        def history(self, token, ticker, start, end):
            assert start == SESSION - timedelta(days=6) and end == upcoming
            return [bar(SESSION), bar(upcoming)]

    with factory() as db:
        assert sync(db, FixtureProvider())["added"] == len(sample())
        before = scan_window(db, ScannerSettings(), upcoming.isoformat())
        db.rollback()
        assert sync(db, Incremental(), clock=lambda: timestamp)["added"] == 1
        after = scan_window(db, ScannerSettings(), upcoming.isoformat())
        assert after != before
        assert (
            db.scalar(select(func.count()).select_from(EodhdCandle))
            == len(sample()) + 1
        )
        db.add(equity("COMI", "EGS60121C018"))
        db.add(
            EodhdCandle(
                ticker="COMI",
                session_date=upcoming.isoformat(),
                isin="EGS60121C018",
                fetched=timestamp.timestamp(),
                bar={},
            )
        )
        db.commit()
        assert scan_window(db, ScannerSettings(), upcoming.isoformat()) != after


def test_utc_boundary_does_not_issue_billable_request(factory):
    provider = FixtureProvider()
    with factory() as db:
        with pytest.raises(ProviderError, match="UTC_RESET_WINDOW"):
            sync(db, provider, clock=lambda: NOW.replace(hour=23, minute=59))
        assert provider.calls == []


def test_catalog_keeps_exact_egx_egp_equity_identities(monkeypatch):
    provider = EodhdProvider()
    row = {
        "Code": "SWDY",
        "Exchange": "EGX",
        "Currency": "EGP",
        "Type": "Common Stock",
        "Isin": service.BOOTSTRAP["SWDY"],
    }
    rows = [
        row,
        row | {"Code": "OTHER", "Currency": "USD"},
        row | {"Code": "NOMATCH", "Exchange": "US"},
    ]
    monkeypatch.setattr(provider, "_fetch", lambda path, token, **params: rows)
    assert provider.catalog(TOKEN) == service.BOOTSTRAP
