from fastapi import APIRouter
from app.api.v1.endpoints import stocks, live_analysis, market, stock_plans, integrations, ai_trading, risk, sharia, scanner, notifications, backtesting, paper_trading

api_router = APIRouter()
api_router.include_router(stocks.router, prefix="/egx/stocks", tags=["EGX Stocks"])
api_router.include_router(live_analysis.router, prefix="/egx/live-analysis", tags=["Live Price Analysis"])
api_router.include_router(market.router, prefix="/egx/market", tags=["Market Status"])
api_router.include_router(stock_plans.router, prefix="/egx/plans", tags=["All Stock Plans"])
api_router.include_router(integrations.router, tags=["Thndr read-only integration"])
api_router.include_router(ai_trading.router, tags=["AI trading analysis"])
api_router.include_router(risk.router, tags=["Portfolio risk"])
api_router.include_router(sharia.router, tags=["Sharia screening"])
api_router.include_router(scanner.router, tags=["Market scanner"])
api_router.include_router(notifications.router, tags=["Scanner notifications"])


api_router.include_router(paper_trading.router, tags=["Virtual paper trading"])
api_router.include_router(backtesting.router, tags=["Historical backtesting"])

from app.api.v1.endpoints import market_data, notification_settings, system

api_router.include_router(notification_settings.router, tags=["Notification delivery"])
api_router.include_router(market_data.router, tags=["Approved market data"])
api_router.include_router(system.router, tags=["Owner system health"])
