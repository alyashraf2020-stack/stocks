import pytest
from app.core.database import SessionLocal, Base, engine
from app.services.seeder import seed_security_master
from app.services.security_master import SecurityMasterService, normalize_arabic

@pytest.fixture(scope="module")
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_security_master(session)
    yield session
    session.close()

def test_security_master_seeded_and_total(db):
    total = SecurityMasterService.get_total_count(db)
    # Full EGX universe must contain at least 150+ listed equities
    assert total >= 150

def test_search_by_ticker(db):
    comi = SecurityMasterService.get_by_ticker(db, "COMI")
    assert comi is not None
    assert comi.ticker == "COMI"
    assert "التجاري الدولي" in comi.arabic_name
    assert "Commercial International Bank" in comi.english_name
    assert comi.sector == "البنوك"

def test_search_by_arabic_name_with_normalization(db):
    # Searching with or without hamza: "ابوقير" vs "أبو قير"
    results1 = SecurityMasterService.get_all(db, query="ابو قير")
    results2 = SecurityMasterService.get_all(db, query="أبو قير")
    assert len(results1) > 0
    assert any(s.ticker == "ABUK" for s in results1)
    assert any(s.ticker == "ABUK" for s in results2)

def test_search_by_english_name(db):
    results = SecurityMasterService.get_all(db, query="Elsewedy")
    assert len(results) > 0
    assert any(s.ticker == "SWDY" for s in results)

def test_reject_non_egx_assets(db):
    # Foreign / US / Crypto / Saudi stocks must never exist
    assert SecurityMasterService.get_by_ticker(db, "AAPL") is None
    assert SecurityMasterService.get_by_ticker(db, "BTC-USD") is None
    assert SecurityMasterService.get_by_ticker(db, "2222.SR") is None
    assert SecurityMasterService.get_by_ticker(db, "EURUSD=X") is None

def test_provenance_preserved(db):
    comi = SecurityMasterService.get_by_ticker(db, "COMI")
    assert comi.source == "The Egyptian Exchange (EGX) Listed Equities Official Registry"
    assert comi.source_updated_at is not None
    assert len(comi.source_updated_at) > 0

def test_index_membership_is_optional_metadata(db):
    # Stocks without index membership must still be in /stocks
    all_stocks = SecurityMasterService.get_all(db)
    non_indexed = [s for s in all_stocks if s.indices == "[]"]
    assert len(non_indexed) > 0  # Multiple listed equities not in EGX30/70/100