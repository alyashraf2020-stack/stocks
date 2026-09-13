import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.security import SecurityResponse, SecurityListResponse
from app.schemas.analysis import ChartResponse, CandleBarResponse
from app.services.security_master import SecurityMasterService
from app.services.data_provider.manager import default_provider_manager
from app.services.indicators import TechnicalIndicatorEngine
from app.services.egx_calendar import (
    get_expected_latest_completed_session,
    calculate_sessions_behind,
    get_freshness_label,
    get_freshness_display_ar,
    CAIRO_TZ
)
from app.models.candle import EGXCandle

router = APIRouter()

@router.get("", response_model=SecurityListResponse)
def get_all_stocks(
    q: Optional[str] = None,
    sector: Optional[str] = None,
    status: Optional[str] = None,
    index_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    securities = SecurityMasterService.get_all(
        db, query=q, sector=sector, status=status, index_filter=index_name, skip=skip, limit=limit
    )

    expected_session = get_expected_latest_completed_session()
    expected_session_str = expected_session.isoformat()

    items = []
    for s in securities:
        sec_dict = s.to_dict()
        
        last_candle = (
            db.query(EGXCandle)
            .filter(EGXCandle.ticker == s.ticker)
            .order_by(EGXCandle.session_date.desc())
            .first()
        )
        if last_candle:
            latest_date = datetime.date.fromisoformat(last_candle.session_date)
            sessions_behind = calculate_sessions_behind(latest_date)
            freshness_ar = get_freshness_display_ar(sessions_behind)
            latest_close = last_candle.close
            latest_session = last_candle.session_date
            actual_provider = last_candle.actual_provider
            analytical_bars_count = (
                db.query(EGXCandle)
                .filter(EGXCandle.ticker == s.ticker)
                .count()
            )
        else:
            sessions_behind = None
            freshness_ar = "غير متاح"
            latest_close = None
            latest_session = None
            actual_provider = None
            analytical_bars_count = 0

        sec_dict["latest_close"] = latest_close
        sec_dict["latest_session_date"] = latest_session
        sec_dict["expected_session_date"] = expected_session_str
        sec_dict["sessions_behind"] = sessions_behind
        sec_dict["freshness"] = freshness_ar
        sec_dict["actual_provider"] = actual_provider
        sec_dict["analytical_bars_count"] = analytical_bars_count
        sec_dict["analysis_available"] = (sessions_behind == 0)
        sec_dict["current_analysis_eligible"] = (sessions_behind == 0 and analytical_bars_count >= 50)
        items.append(sec_dict)

    first_sec = securities[0] if securities else None
    prov_src = first_sec.source if first_sec else "The Egyptian Exchange (EGX) Official Registry"
    prov_time = first_sec.source_updated_at if first_sec else "2026-09-10T14:30:00+02:00"

    return {
        "total": len(items),
        "provenance_source": prov_src,
        "provenance_updated_at": prov_time,
        "items": items
    }

@router.get("/sectors", response_model=List[str])
def get_all_sectors(db: Session = Depends(get_db)):
    return SecurityMasterService.get_sectors(db)

@router.get("/{ticker}", response_model=SecurityResponse)
def get_stock_by_ticker(ticker: str, db: Session = Depends(get_db)):
    sec = SecurityMasterService.get_by_ticker(db, ticker)
    if not sec:
        raise HTTPException(status_code=404, detail=f"سهم {ticker} غير مدرج في البورصة المصرية")

    # Fetch canonical data via ProviderManager (checks zero-lag cache first, fetches provider if needed)
    data_res = default_provider_manager.get_analytical_bars(sec.ticker, limit=250, db=db)

    sec_dict = sec.to_dict()
    sec_dict["expected_session_date"] = data_res.get("expected_latest_session")
    sec_dict["latest_session_date"] = data_res.get("latest_session")
    sec_dict["sessions_behind"] = data_res.get("sessions_behind")
    sec_dict["freshness"] = data_res.get("freshness_ar", "غير متاح")
    sec_dict["actual_provider"] = data_res.get("actual_provider")
    sec_dict["analytical_bars_count"] = data_res.get("analytical_bars_count")
    sec_dict["analysis_available"] = (data_res.get("sessions_behind") == 0)
    sec_dict["current_analysis_eligible"] = data_res.get("current_analysis_eligible", False)

    bars = data_res.get("bars", [])
    sec_dict["latest_close"] = bars[-1]["close"] if bars else None

    return sec_dict

@router.post("/{ticker}/refresh", response_model=SecurityResponse)
def refresh_stock_data(ticker: str, db: Session = Depends(get_db)):
    sec = SecurityMasterService.get_by_ticker(db, ticker)
    if not sec:
        raise HTTPException(status_code=404, detail=f"سهم {ticker} غير مدرج في البورصة المصرية")

    # Force fresh pull from provider pipeline and update database candles
    data_res = default_provider_manager.get_analytical_bars(sec.ticker, limit=250, db=db, force_refresh=True)

    sec_dict = sec.to_dict()
    sec_dict["expected_session_date"] = data_res.get("expected_latest_session")
    sec_dict["latest_session_date"] = data_res.get("latest_session")
    sec_dict["sessions_behind"] = data_res.get("sessions_behind")
    sec_dict["freshness"] = data_res.get("freshness_ar", "غير متاح")
    sec_dict["actual_provider"] = data_res.get("actual_provider")
    sec_dict["analytical_bars_count"] = data_res.get("analytical_bars_count")
    sec_dict["analysis_available"] = (data_res.get("sessions_behind") == 0)
    sec_dict["current_analysis_eligible"] = data_res.get("current_analysis_eligible", False)

    bars = data_res.get("bars", [])
    sec_dict["latest_close"] = bars[-1]["close"] if bars else None

    return sec_dict

@router.get("/{ticker}/chart", response_model=ChartResponse)
def get_stock_chart(
    ticker: str,
    range: str = Query("3M", pattern="^(1W|1M|3M|6M|1Y)$"),
    db: Session = Depends(get_db)
):
    sec = SecurityMasterService.get_by_ticker(db, ticker)
    if not sec:
        raise HTTPException(status_code=404, detail=f"سهم {ticker} غير مدرج في البورصة المصرية")

    data_res = default_provider_manager.get_analytical_bars(sec.ticker, limit=250, db=db)
    if data_res["status"] == "DATA_UNAVAILABLE" or not data_res["bars"]:
        raise HTTPException(status_code=404, detail="البيانات التاريخية غير متاحة لهذا السهم حالياً")

    # Calculate indicators on full history BEFORE slicing
    enriched_full = TechnicalIndicatorEngine.compute_all_indicators(data_res["bars"])

    range_map = {
        "1W": 5,
        "1M": 22,
        "3M": 65,
        "6M": 130,
        "1Y": 250
    }
    slice_count = range_map.get(range, 65)
    sliced_bars = enriched_full[-slice_count:] if len(enriched_full) > slice_count else enriched_full

    return {
        "ticker": sec.ticker,
        "range_selected": range,
        "total_bars": len(sliced_bars),
        "expected_latest_session": data_res["expected_latest_session"],
        "latest_available_session": data_res["latest_session"],
        "latest_close": sliced_bars[-1]["close"] if sliced_bars else None,
        "sessions_behind": data_res["sessions_behind"],
        "freshness": data_res["freshness"],
        "freshness_ar": data_res.get("freshness_ar", "غير محدث"),
        "actual_provider": data_res.get("actual_provider"),
        "bars": sliced_bars
    }