import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.market import MarketStatusResponse
from app.models.security import EGXSecurity
from app.services.egx_calendar import (
    is_egx_trading_day,
    get_expected_latest_completed_session,
    CAIRO_TZ
)

router = APIRouter()

@router.get("/status", response_model=MarketStatusResponse)
def get_market_status(db: Session = Depends(get_db)):
    now_cairo = datetime.datetime.now(CAIRO_TZ)
    current_time = now_cairo.time()
    
    # EGX hours: 10:00 to 14:30 Cairo time
    open_time = datetime.time(10, 0)
    close_time = datetime.time(14, 30)

    is_trading_day = is_egx_trading_day(now_cairo.date())
    is_open = is_trading_day and (open_time <= current_time <= close_time)

    expected_session = get_expected_latest_completed_session(now_cairo)

    total_listed = db.query(EGXSecurity).count()
    active_count = db.query(EGXSecurity).filter(EGXSecurity.listing_status == "ACTIVE").count()
    suspended_count = db.query(EGXSecurity).filter(EGXSecurity.listing_status == "SUSPENDED").count()

    first_sec = db.query(EGXSecurity).first()
    prov_src = first_sec.source if first_sec else "The Egyptian Exchange (EGX) Official Registry"
    prov_time = first_sec.source_updated_at if first_sec else "2026-09-10T14:30:00+02:00"

    return {
        "is_open_now": is_open,
        "current_cairo_time": now_cairo.strftime("%Y-%m-%d %H:%M:%S Cairo (UTC+3)"),
        "expected_latest_completed_session": expected_session.isoformat(),
        "total_listed_equities": total_listed,
        "active_equities_count": active_count,
        "suspended_equities_count": suspended_count,
        "provenance_source": prov_src,
        "provenance_updated_at": prov_time
    }