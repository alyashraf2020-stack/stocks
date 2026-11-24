from concurrent.futures import ThreadPoolExecutor
from datetime import date
import sqlite3

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.sqlite_backup import backup_database
from app.main import app
from app.models.candle_revision import CandleRevision
from app.models.security import EGXSecurity
from app.services.egx_calendar import calculate_sessions_behind, CAIRO_TZ
from app.services.validator import completed_analytical_bars

SESSION = date(2026, 11, 23)
BAR = dict(ticker="AMES", session_date=SESSION.isoformat(), open=10, low=9, high=12, close=11, volume=100)


@pytest.mark.parametrize("changes", [
    {"ticker": "OTHER"}, {"ticker": None}, {"session_date": "2026-11-24"},
    {"session_date": "2026-11-20"}, {"session_date": "20261123"},
    {"currency": "USD"}, {"exchange": "OTHER"}, {"high": float("inf")},
    {"volume": float("nan")}, {"open": float("inf")}, {"volume": None},
    {"volume": "unavailable"}, {"volume": True}, {"validation_status": "INVALID"},
])
def test_unusable_rows_cannot_supply_the_latest_price(changes):
    assert not completed_analytical_bars([{**BAR, **changes}], SESSION, "AMES")


def test_missing_volume_is_distinct_from_zero_and_conflicts_fail_closed():
    missing = BAR.copy()
    del missing["volume"]
    assert not completed_analytical_bars([missing], SESSION, "AMES")
    assert completed_analytical_bars([{**BAR, "volume": 0}], SESSION, "AMES")
    assert not completed_analytical_bars([BAR, {**BAR, "close": 12}], SESSION, "AMES")
    assert len(completed_analytical_bars([BAR, BAR], SESSION, "AMES")) == 1


def test_future_close_has_unknown_lag():
    from datetime import datetime
    now = datetime(2026, 11, 23, 15, tzinfo=CAIRO_TZ)
    assert calculate_sessions_behind(date(2026, 11, 24), now) is None


def test_concurrent_verified_backups_preserve_local_data(tmp_path):
    source, target = tmp_path / "source.db", tmp_path / "instance" / "live.db"
    conn = sqlite3.connect(source)
    try:
        conn.execute("CREATE TABLE marker(value INTEGER)")
        conn.execute("INSERT INTO marker VALUES (7)")
        conn.commit()

        def initialize(_):
            try:
                backup_database(source, target)
            except FileExistsError:
                return False
            return True

        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(initialize, range(2))) == [False, True]
        copy = sqlite3.connect(target)
        try:
            assert copy.execute("SELECT value FROM marker").fetchone() == (7,)
            copy.execute("UPDATE marker SET value=8")
            copy.commit()
            with pytest.raises(FileExistsError):
                backup_database(source, target)
            assert copy.execute("SELECT value FROM marker").fetchone() == (8,)
            assert conn.execute("SELECT value FROM marker").fetchone() == (7,)
        finally:
            copy.close()
    finally:
        conn.close()


def test_manual_eod_journal_is_atomic_and_retries_do_not_duplicate(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.live_analysis.get_expected_latest_completed_session", lambda: SESSION)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(EGXSecurity(ticker="AMES", arabic_name="شركة", english_name="Test", sector="Test", source_updated_at="2026-11-23"))
        db.commit()
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session
    try:
        client = TestClient(app)
        url = "/api/v1/egx/live-analysis/manual-eod"
        for price in (11, 12, 12):
            assert client.post(url, json={**BAR, "close": price}).status_code == 200
        assert client.post(url, json={**BAR, "close": 25}).status_code == 400
        with Session(engine) as db:
            first, second = db.query(CandleRevision).order_by(CandleRevision.id).all()
            assert first.before is None and first.after["close"] == 11
            assert second.before["close"] == 11 and second.after["close"] == 12
    finally:
        del app.dependency_overrides[get_db]
        engine.dispose()


def test_untrusted_browser_cannot_write_through_local_api():
    response = TestClient(app).post("/api/v1/egx/live-analysis/manual-eod",
                                    headers={"Origin": "https://untrusted.example"}, json={})
    assert response.status_code == 403


def test_fallback_rejects_wrong_instrument_on_single_session_recovery():
    from unittest.mock import Mock
    from app.services.data_provider.manager import ProviderManager
    provider = Mock(provider_name="fixture")
    provider.fetch_session_bar.return_value = {**BAR, "ticker": "OTHER"}
    manager = ProviderManager(primary_provider=provider, fallback_providers=[provider])
    assert manager._recover_one_missing_session([], "AMES", BAR["session_date"], None) == (None, None)


def test_migration_preserves_legacy_tables_on_repeat(tmp_path, monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    from app.core.config import LEGACY_DATABASE

    dest = tmp_path / "market.db"
    backup_database(LEGACY_DATABASE, dest)
    conn = sqlite3.connect(dest)
    try:
        def existing_data():
            return [conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                    for table in ("egx_candles", "egx_securities")]
        original = existing_data()
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{dest.as_posix()}")
        for _ in range(2):
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True,
                           cwd=Path(__file__).resolve().parents[1])
        assert existing_data() == original
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002_portfolio_policy",)
        assert conn.execute("SELECT count(*) FROM egx_candle_revisions").fetchone() == (0,)
    finally:
        conn.close()


def test_legacy_database_url_redirects_to_a_verified_private_copy(tmp_path, monkeypatch):
    from app.core import database

    legacy, private = tmp_path / "legacy.db", tmp_path / "instance" / "new.db"
    conn = sqlite3.connect(legacy)
    conn.execute("CREATE TABLE owner_local_history(value INTEGER)")
    conn.execute("INSERT INTO owner_local_history VALUES (42)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "LEGACY_DATABASE", legacy)
    monkeypatch.setattr(database, "RUNTIME_DATABASE", private)
    engine = database.create_database_engine(f"sqlite:///{legacy.as_posix()}")
    try:
        with engine.begin() as tx:
            assert tx.exec_driver_sql("SELECT value FROM owner_local_history").scalar_one() == 42
            tx.exec_driver_sql("UPDATE owner_local_history SET value=43")
    finally:
        engine.dispose()
    conn = sqlite3.connect(legacy)
    try:
        assert conn.execute("SELECT value FROM owner_local_history").fetchone() == (42,)
    finally:
        conn.close()
