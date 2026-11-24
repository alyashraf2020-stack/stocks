import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.integrations import owner, portfolio
from app.core.database import get_db
from app.integrations.openai_client import AISettings
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import Analysis, AnalysisRequest
from app.services.ai_budget_manager import AIBudgetManager
from app.services.ai_context_builder import build_analysis
from app.services.ai_decision_engine import explain
from app.services.ai_opportunities import opportunities, rank

router = APIRouter(prefix="/ai-trading", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


@router.get("/status")
def status():
    config = AISettings()
    try:
        usage = AIBudgetManager().usage()
    except (OSError, sqlite3.Error):
        usage = None
    return dict(
        status=config.status,
        model=config.OPENAI_MODEL,
        usage=usage,
        daily_limit_usd=float(config.AI_DAILY_BUDGET_USD),
        monthly_limit_usd=float(config.AI_MONTHLY_BUDGET_USD),
    )


@router.post("/analyze", response_model=Analysis)
async def analyze(data: AnalysisRequest, request: Request, db: DB):
    brokerage = await portfolio() if data.source == "THNDR" else None

    def evaluate():
        security = db.get(EGXSecurity, data.ticker)
        if security is None:
            raise HTTPException(404, "UNKNOWN_SYMBOL")
        report = build_analysis(db, security, data, brokerage)
        return explain(
            report, data, AISettings(), request.headers["X-EGX-Gateway"].encode()
        )

    return await run_in_threadpool(evaluate)


@router.get("/opportunities")
async def ranked(db: DB, include_portfolio: bool = False):
    brokerage = await portfolio() if include_portfolio else None
    return await run_in_threadpool(opportunities, db, brokerage)


@router.post("/portfolio", response_model=list[Analysis])
async def analyze_portfolio(request: Request, db: DB):
    brokerage = await portfolio()

    def evaluate():
        if not brokerage.holdings:
            return []
        symbols = sorted({holding.ticker for holding in brokerage.holdings})[:25]
        results = []
        for ticker in symbols:
            security = db.get(EGXSecurity, ticker)
            if security:
                data = AnalysisRequest(ticker=ticker, source="THNDR")
                results.append((data, build_analysis(db, security, data, brokerage)))
        candidates = [
            (row["score"], data.ticker)
            for data, report in results
            if (row := rank(report))
        ]
        selected = max(candidates, default=(0, None))[1]
        cfg = AISettings()
        return [
            explain(
                report,
                data.model_copy(update={"explain": data.ticker == selected}),
                cfg,
                request.headers["X-EGX-Gateway"].encode(),
            )
            for data, report in results
        ]

    return await run_in_threadpool(evaluate)
