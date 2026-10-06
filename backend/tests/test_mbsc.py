import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.security import EGXSecurity
from app.services.company_profile import parse_snapshot, get_mbsc_company_profile
from app.services.data_provider.investing_provider import INVESTING_INSTRUMENT_MAP
from app.services.security_master import SecurityMasterService
from app.services.seeder import seed_security_master


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_existing_database_backfills_mbsc_without_overwriting_or_duplicates(db):
    db.add(EGXSecurity(ticker="COMI", arabic_name="اسم محفوظ", english_name="Saved name",
                       sector="البنوك", source="saved", source_updated_at="2026-01-01"))
    db.commit()
    total = seed_security_master(db)
    assert total == seed_security_master(db)
    assert db.get(EGXSecurity, "COMI").arabic_name == "اسم محفوظ"
    mbsc = db.get(EGXSecurity, "MBSC")
    assert mbsc.isin == "EGS3C371C019"
    for query in ["MBSC", "مصر بني سويف", "مصر بنى سويف", "Misr Beni Suef"]:
        assert any(s.ticker == "MBSC" for s in SecurityMasterService.get_all(db, query=query))
    assert INVESTING_INSTRUMENT_MAP["MBSC"] == 12965


def snapshot_html(symbol="MBSC", isin="EGS3C371C019", currency="EGP"):
    instrument = {"name": {"symbol": symbol}, "underlying": {"isin": isin},
                  "price": {"currency": currency, "last": 10, "lastUpdateTime": 1791199019000,
                            "isDelayed": True}, "fundamental": {"eps": "NaN", "ratio": 0}}
    payload = {"props": {"pageProps": {"state": {"equityStore": {"instrument": instrument}}}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'


def test_snapshot_preserves_zero_missing_values_and_quote_time():
    snapshot = parse_snapshot(snapshot_html())
    assert snapshot["metrics"]["pe_ratio"] == 0
    assert snapshot["metrics"]["eps"] is None
    assert snapshot["metrics"]["market_cap"] is None
    assert snapshot["quote_updated_at"].endswith("+00:00")
    assert snapshot["is_delayed"] is True


@pytest.mark.parametrize("kwargs", [{"symbol": "OTHER"}, {"isin": "OTHER"}, {"currency": "USD"}])
def test_snapshot_rejects_wrong_security_or_currency(kwargs):
    with pytest.raises(ValueError):
        parse_snapshot(snapshot_html(**kwargs))


def test_company_provider_outage_retains_identity_and_resource_links():
    with patch("curl_cffi.requests.Session.get", side_effect=RuntimeError("offline")):
        profile = get_mbsc_company_profile()
    assert profile["status"] == "UNAVAILABLE"
    assert profile["metrics"] == {}
    assert profile["quote_updated_at"] is None
    assert len(profile["resources"]) == 5


def test_company_api_and_search(db):
    seed_security_master(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("app.api.v1.endpoints.stocks.get_mbsc_company_profile", return_value={"ticker": "MBSC"}):
            client = TestClient(app)
            result = client.get("/api/v1/egx/stocks?q=مصر بني سويف")
            assert result.status_code == 200
            assert result.json()["items"][0]["ticker"] == "MBSC"
            assert client.get("/api/v1/egx/stocks/mbsc/company").json()["ticker"] == "MBSC"
            assert client.get("/api/v1/egx/stocks/AAPL/company").status_code == 404
    finally:
        app.dependency_overrides.clear()
