import datetime
import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity
from app.models.security_data_correction import SecurityDataCorrection
from app.services.company_profile import BIOC_ISIN, BIOC_URL, get_bioc_company_profile, parse_snapshot
from app.services.data_provider.investing_provider import InvestingHistoricalProvider
from app.services.data_provider.investing_legacy_provider import InvestingLegacySearchProvider
from app.services.data_provider.manager import ProviderManager
from app.services.security_master import SecurityMasterService
from app.services.seeder import seed_security_master
from tests.test_mbsc import snapshot_html


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def candle(ticker="BIOC", close=1.0, provider="Old ambiguous source"):
    return EGXCandle(ticker=ticker, session_date="2026-10-05", open=close,
                     high=close + 0.1, low=close - 0.1, close=close,
                     volume=100000, actual_provider=provider)


def old_security():
    return EGXSecurity(ticker="BIOC", arabic_name="بيوجينكس فارما", english_name="Biogenyx Pharma",
                       isin="EGS72AV1C011", sector="الرعاية الصحية والأدوية", listing_status="ACTIVE",
                       indices=json.dumps(["تميز"]), source="old", source_updated_at="2026-09-10")


def test_existing_identity_and_prices_are_corrected_and_archived_once(db):
    db.add_all([old_security(), candle(), candle("COMI", 100),
                EGXSecurity(ticker="COMI", arabic_name="اسم محفوظ", english_name="Saved",
                            sector="البنوك", source="saved", source_updated_at="2026-01-01")])
    db.commit()
    count = seed_security_master(db)
    db.expire_all()
    security = db.get(EGXSecurity, "BIOC")
    assert security.arabic_name == "جلاكسو سميث كلاين"
    assert security.english_name == "GlaxoSmithKline SAE"
    assert security.isin == BIOC_ISIN
    assert json.loads(security.indices) == []
    assert db.get(EGXSecurity, "COMI").arabic_name == "اسم محفوظ"
    assert db.query(EGXCandle).filter_by(ticker="COMI").one().close == 100
    assert db.query(EGXCandle).filter_by(ticker="BIOC").count() == 0
    correction = db.query(SecurityDataCorrection).one()
    archive = json.loads(correction.archived_data)
    assert archive["previous_security"]["isin"] == "EGS72AV1C011"
    assert archive["previous_candles"][0]["close"] == 1
    original_archive = correction.archived_data

    db.add(candle(close=350, provider="Investing Historical"))
    db.commit()
    assert seed_security_master(db) == count
    assert db.query(EGXCandle).filter_by(ticker="BIOC").one().close == 350
    assert db.query(SecurityDataCorrection).count() == 1
    assert correction.archived_data == original_archive


def test_fresh_install_does_not_clear_prices_on_second_start(db):
    seed_security_master(db)
    assert json.loads(db.query(SecurityDataCorrection).one().archived_data)["previous_security"] is None
    db.add(candle(close=350, provider="Investing Historical"))
    db.commit()
    seed_security_master(db)
    assert db.query(EGXCandle).filter_by(ticker="BIOC").one().close == 350


def test_previously_fixed_name_does_not_keep_unverified_prices(db):
    security = old_security()
    security.arabic_name = "جلاكسو سميث كلاين"
    security.isin = BIOC_ISIN
    db.add_all([security, candle()])
    db.commit()
    seed_security_master(db)
    assert db.query(EGXCandle).filter_by(ticker="BIOC").count() == 0
    assert len(json.loads(db.query(SecurityDataCorrection).one().archived_data)["previous_candles"]) == 1


@pytest.mark.parametrize("provider_class", [InvestingHistoricalProvider, InvestingLegacySearchProvider])
def test_verified_mapping_overrides_ambiguous_cached_resolution(monkeypatch, provider_class):
    monkeypatch.setattr(InvestingHistoricalProvider, "_resolved_cache", {"BIOC": 999999})
    monkeypatch.setattr(InvestingHistoricalProvider, "_resolved_url_cache", {"BIOC": "https://www.investing.com/equities/foreign-company"})
    provider = provider_class()
    with patch("curl_cffi.requests.Session.get", side_effect=AssertionError("Must not search an ambiguous symbol")):
        assert provider._resolve_instrument_id("bioc", "Biogenyx Pharma") == 12975
        assert provider._resolve_metadata("BIOC") == {"id": 12975, "url": BIOC_URL}
    with patch.object(provider, "_fetch_chart", return_value=[]) as fetch:
        with patch.object(provider, "_fetch_bioc_page_history", return_value=[]):
            provider.fetch_historical_bars("BIOC", limit=160)
    fetch.assert_called_once_with("BIOC", 12975, 160)


def history_html(instrument_changes=None, row_changes=None):
    instrument = {"base": {"id": "12975"}, "name": {"symbol": "BIOC"},
                  "underlying": {"isin": BIOC_ISIN, "market": "Egypt"}, "price": {"currency": "EGP", "last": 999}}
    for path, value in (instrument_changes or {}).items():
        section, key = path.split(".")
        instrument[section][key] = value
    row = {"rowDateTimestamp": "2026-10-05T00:00:00Z", "last_openRaw": "352",
           "last_maxRaw": "359", "last_minRaw": "338", "last_closeRaw": "339", "volumeRaw": 272273}
    row.update(row_changes or {})
    state = {"equityStore": {"instrument": instrument}, "historicalDataStore": {"historicalData": {"data": [row]}}}
    return '<script id="__NEXT_DATA__">' + json.dumps({"props": {"pageProps": {"state": state}}}) + '</script>'


def test_page_fallback_reads_explicit_completed_rows_not_quote(monkeypatch):
    monkeypatch.setattr("app.services.egx_calendar.get_expected_latest_completed_session", lambda: datetime.date(2026, 10, 5))
    bars = InvestingHistoricalProvider._parse_bioc_page_history(history_html())
    assert len(bars) == 1
    assert bars[0]["close"] == 339
    assert bars[0]["session_date"] == "2026-10-05"
    assert "Verified BIOC" in bars[0]["actual_provider"]
    with patch.object(InvestingHistoricalProvider, "_fetch_chart", return_value=[]), patch("curl_cffi.requests.Session.get", return_value=Mock(text=history_html())):
        assert InvestingHistoricalProvider().fetch_historical_bars("BIOC")[0]["close"] == 339


@pytest.mark.parametrize("changes", [{"name.symbol": "OTHER"}, {"underlying.isin": "OTHER"},
                                      {"underlying.market": "United States"}, {"price.currency": "USD"},
                                      {"base.id": "999999"}])
def test_page_fallback_rejects_wrong_identity(changes):
    assert InvestingHistoricalProvider._parse_bioc_page_history(history_html(instrument_changes=changes)) == []


@pytest.mark.parametrize("changes", [{"rowDateTimestamp": "2026-10-07T00:00:00Z"},
                                      {"last_closeRaw": "NaN"}, {"last_minRaw": "0"},
                                      {"volumeRaw": -1}, {"last_maxRaw": "330"}])
def test_page_fallback_rejects_future_or_invalid_rows(monkeypatch, changes):
    monkeypatch.setattr("app.services.egx_calendar.get_expected_latest_completed_session", lambda: datetime.date(2026, 10, 5))
    assert InvestingHistoricalProvider._parse_bioc_page_history(history_html(row_changes=changes)) == []


def test_bioc_uses_verified_investing_before_generic_providers(monkeypatch):
    import app.services.data_provider.manager as manager_module
    expected = datetime.date(2026, 10, 5)
    monkeypatch.setattr(manager_module, "get_expected_latest_completed_session", lambda now=None: expected)
    monkeypatch.setattr(manager_module, "calculate_sessions_behind", lambda latest, now=None: 0 if latest == expected else 1)
    provider = InvestingHistoricalProvider()
    manager = ProviderManager(primary_provider=Mock(), fallback_providers=[provider])
    verified_bar = candle(close=350, provider="Investing Historical").to_dict()
    fetch = Mock(side_effect=lambda provider, **kwargs: [verified_bar] if isinstance(provider, InvestingHistoricalProvider) else pytest.fail("Generic provider used first"))
    monkeypatch.setattr(manager, "_fetch_provider_bars", fetch)
    result = manager.get_raw_historical_bars("BIOC", force_refresh=True)
    assert result["bars"][-1]["close"] == 350
    assert fetch.call_count == 1


@pytest.mark.parametrize("kwargs", [{"symbol": "OTHER"}, {"isin": "EGS72AV1C011"}, {"currency": "USD"}])
def test_bioc_snapshot_rejects_other_companies_or_currency(kwargs):
    payload = {"symbol": "BIOC", "isin": BIOC_ISIN, **kwargs}
    with pytest.raises(ValueError):
        parse_snapshot(snapshot_html(**payload), ticker="BIOC", isin=BIOC_ISIN)


def test_bioc_profile_outage_does_not_substitute_a_price():
    with patch("curl_cffi.requests.Session.get", side_effect=RuntimeError("offline")):
        profile = get_bioc_company_profile()
    assert profile["ticker"] == "BIOC"
    assert profile["status"] == "UNAVAILABLE"
    assert profile["metrics"] == {}
    assert profile["quote_updated_at"] is None
    assert profile["metrics_source"] == BIOC_URL
    assert any(link["url"] == "https://www.gsk.com/en-gb/locations/egypt/" for link in profile["resources"])


def test_corrected_bioc_appears_in_search_company_and_all_plans(db):
    db.add_all([old_security(), candle()])
    db.commit()
    seed_security_master(db)
    for query in ["BIOC", "جلاكسو", "سميث كلاين", "GlaxoSmithKline", BIOC_ISIN]:
        assert any(s.ticker == "BIOC" for s in SecurityMasterService.get_all(db, query=query))
    assert not SecurityMasterService.get_all(db, query="بيوجينكس")
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        stock = client.get("/api/v1/egx/stocks?q=جلاكسو").json()["items"][0]
        assert stock["isin"] == BIOC_ISIN
        assert stock["latest_close"] is None
        row = next(row for row in client.get("/api/v1/egx/plans").json()["items"] if row["ticker"] == "BIOC")
        assert row["arabic_name"] == "جلاكسو سميث كلاين"
        assert row["trade_plan"] is None
        with patch("app.api.v1.endpoints.stocks.get_bioc_company_profile", return_value={"ticker": "BIOC"}):
            assert client.get("/api/v1/egx/stocks/bioc/company").json()["ticker"] == "BIOC"
    finally:
        app.dependency_overrides.clear()
