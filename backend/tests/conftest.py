"""Every pytest invocation owns its database. External feed checks are opt-in."""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import time_machine

_test_store = tempfile.TemporaryDirectory(prefix="egx-tests-")
_backend = Path(__file__).resolve().parents[1]
_database = Path(_test_store.name) / "market.db"
shutil.copyfile(_backend / "egx_platform.db", _database)
os.environ["DATABASE_URL"] = f"sqlite:///{_database.as_posix()}"


@pytest.fixture(scope="session", autouse=True)
def seed_directory():
    from app.core.database import SessionLocal, engine
    from app.services.seeder import seed_security_master

    with SessionLocal() as db:
        seed_security_master(db)
    yield
    engine.dispose()


@pytest.fixture
def local_market(monkeypatch):
    """Test the real cache, indicators and endpoints on known completed COMI sessions."""
    from app.core.database import SessionLocal
    from app.models.candle import EGXCandle
    from app.services.data_provider.manager import default_provider_manager
    from app.services.egx_calendar import CAIRO_TZ

    from tests.test_stock_plans import bars

    with time_machine.travel(datetime(2026, 11, 23, 16, tzinfo=CAIRO_TZ), tick=False):
        history = bars(end=datetime(2026, 11, 23).date(), count=80)
        with SessionLocal() as db:
            db.query(EGXCandle).filter_by(ticker="COMI").delete()
            db.add_all(EGXCandle(**row) for row in history)
            db.commit()
        monkeypatch.setattr(
            default_provider_manager,
            "_fetch_provider_bars",
            lambda **kw: history if kw["ticker"] == "COMI" else [],
        )
        yield
