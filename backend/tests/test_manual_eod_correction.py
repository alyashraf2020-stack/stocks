import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.live_analysis import save_manual_eod
from app.core.database import Base
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity
from app.schemas.live_analysis import ManualEODRequest


def test_manual_eod_can_replace_wrong_current_provider_candle():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(
                EGXSecurity(
                    ticker="AMES",
                    arabic_name="الإسكندرية للخدمات الطبية",
                    english_name="Alexandria Medical Services",
                    isin="EGS72081C010",
                    sector="الرعاية الصحية والأدوية",
                    listing_status="ACTIVE",
                    indices="[]",
                    source="EGX",
                    source_updated_at="2026-11-11T00:00:00+02:00",
                )
            )
            db.add(
                EGXCandle(
                    ticker="AMES",
                    session_date="2026-11-11",
                    open=50.0,
                    high=56.0,
                    low=49.0,
                    close=55.11,
                    volume=100_000,
                    actual_provider="Yahoo Finance EGX + DirectFN EGX",
                    validation_status="VALID",
                )
            )
            db.commit()

            request = ManualEODRequest(
                ticker="AMES",
                session_date="2026-11-11",
                open=47.60,
                high=52.70,
                low=47.60,
                close=51.10,
                volume=11_573_411,
            )
            with patch(
                "app.api.v1.endpoints.live_analysis.get_expected_latest_completed_session",
                return_value=datetime.date(2026, 11, 11),
            ):
                result = save_manual_eod(request, db)

            corrected = (
                db.query(EGXCandle)
                .filter(
                    EGXCandle.ticker == "AMES",
                    EGXCandle.session_date == "2026-11-11",
                )
                .one()
            )
            assert result["status"] == "SUCCESS"
            assert corrected.close == 51.10
            assert corrected.open == 47.60
            assert corrected.high == 52.70
            assert corrected.low == 47.60
            assert corrected.volume == 11_573_411
            assert corrected.actual_provider == "USER_VERIFIED_EOD"
    finally:
        engine.dispose()
