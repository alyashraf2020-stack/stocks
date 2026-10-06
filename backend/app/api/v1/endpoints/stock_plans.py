from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from threading import BoundedSemaphore
from app.core.database import get_db
from app.schemas.stock_plans import StockPlanResponse, StockPlansResponse
from app.services.security_master import SecurityMasterService
from app.services.stock_plans import StockPlansService

router = APIRouter()
refresh_slots = BoundedSemaphore(3)


@router.get("", response_model=StockPlansResponse)
def get_all_plans(db: Session = Depends(get_db)):
    # Immediately calculate the entire directory from validated cached EOD bars.
    # Provider requests are explicit per-symbol operations, so one slow symbol
    # cannot delay or remove the rest of the table.
    return StockPlansService.overview(db)


@router.post("/{ticker}/refresh", response_model=StockPlanResponse)
def refresh_plan(ticker: str, db: Session = Depends(get_db)):
    security = SecurityMasterService.get_by_ticker(db, ticker)
    if not security:
        raise HTTPException(status_code=404, detail="السهم غير موجود في دليل البورصة المصرية")
    if not refresh_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="جاري تحديث أسهم أخرى. انتظر اكتمالها ثم أعد المحاولة.")
    try:
        return StockPlansService.build(db, security, refresh=True)
    finally:
        refresh_slots.release()
