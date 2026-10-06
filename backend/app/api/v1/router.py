from fastapi import APIRouter
from app.api.v1.endpoints import stocks, live_analysis, market, stock_plans

api_router = APIRouter()
api_router.include_router(stocks.router, prefix="/egx/stocks", tags=["EGX Stocks"])
api_router.include_router(live_analysis.router, prefix="/egx/live-analysis", tags=["Live Price Analysis"])
api_router.include_router(market.router, prefix="/egx/market", tags=["Market Status"])
api_router.include_router(stock_plans.router, prefix="/egx/plans", tags=["All Stock Plans"])
