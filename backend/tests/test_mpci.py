from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.security import EGXSecurity
from app.services.company_profile import MPCI_ISIN, get_mpci_company_profile, parse_snapshot
from app.services.data_provider.investing_provider import INVESTING_INSTRUMENT_MAP
from app.services.security_master import SecurityMasterService
from app.services.seeder import seed_security_master
from tests.test_mbsc import snapshot_html


def test_existing_database_backfills_mpci_and_preserves_existing_stocks():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(EGXSecurity(ticker="COMI", arabic_name="اسم محفوظ", english_name="Saved",
                               sector="البنوك", source="saved", source_updated_at="2026-01-01"))
            db.commit()
            count = seed_security_master(db)
            assert seed_security_master(db) == count
            assert db.get(EGXSecurity, "COMI").arabic_name == "اسم محفوظ"
            assert db.get(EGXSecurity, "MBSC") is not None
            assert db.get(EGXSecurity, "MPCI").isin == MPCI_ISIN
            for query in ["MPCI", "ممفيس", "Memphis"]:
                assert any(s.ticker == "MPCI" for s in SecurityMasterService.get_all(db, query=query))
            assert INVESTING_INSTRUMENT_MAP["MPCI"] == 40612
            app.dependency_overrides[get_db] = lambda: db
            try:
                client = TestClient(app)
                assert any(s["ticker"] == "MPCI" for s in client.get("/api/v1/egx/plans").json()["items"])
                with patch("app.api.v1.endpoints.stocks.get_mpci_company_profile", return_value={"ticker": "MPCI"}):
                    assert client.get("/api/v1/egx/stocks/mpci/company").json()["ticker"] == "MPCI"
            finally:
                app.dependency_overrides.clear()
    finally:
        engine.dispose()


def test_mpci_snapshot_rejects_a_different_stock():
    assert parse_snapshot(snapshot_html(symbol="MPCI", isin=MPCI_ISIN), ticker="MPCI", isin=MPCI_ISIN)["metrics"]["price"] == 10
    with pytest.raises(ValueError):
        parse_snapshot(snapshot_html(), ticker="MPCI", isin=MPCI_ISIN)


def test_mpci_outage_retains_company_identity_and_links():
    with patch("curl_cffi.requests.Session.get", side_effect=RuntimeError("offline")):
        profile = get_mpci_company_profile()
    assert profile["status"] == "UNAVAILABLE"
    assert profile["ticker"] == "MPCI"
    assert profile["metrics"] == {}
    assert profile["listed_on"] is None
    assert "memphis-pharmaceuticals" in profile["metrics_source"]
