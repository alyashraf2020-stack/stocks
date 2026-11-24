from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.v1.endpoints.integrations import owner, portfolio
from app.core.database import get_db
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import AnalysisRequest
from app.schemas.risk import Candidate, PortfolioSnapshot, RiskPolicy, RiskReviewRequest
from app.services.ai_context_builder import build_analysis
from app.services.portfolio_risk import brokerage_snapshot, dec, summarize
from app.services.risk_policy import (
    calculate_size,
    entry_blocks,
    load_policy,
    save_policy,
)
from app.services.risk_scenarios import review_position
from app.services.sharia_filter import status_for

router = APIRouter(prefix="/risk", dependencies=[Depends(owner)])
DB = Annotated[Session, Depends(get_db)]


@router.get("/settings", response_model=RiskPolicy)
def get_settings(db: DB):
    return load_policy(db)


@router.post("/settings", response_model=RiskPolicy)
def update_settings(policy: RiskPolicy, db: DB):
    save_policy(db, policy)
    return policy


def size_from_analysis(
    db, security, analysis, snapshot, sectors, policy, source, *, adding=False,
    screening_status=None, as_of=None,
):
    status = (screening_status or status_for(db, security)["status"]) if policy.islamic_mode else None
    blockers = entry_blocks(policy, status, advanced_supported=True)
    if (
        not analysis.levels
        or analysis.signal in {"DATA_NOT_CURRENT", "INSUFFICIENT_DATA", "NO_TRADE"}
        or analysis.freshness not in {"HISTORICAL", "REALTIME_VERIFIED"}
        or analysis.market_status == "HALTED"
    ):
        blockers.append("CURRENT_TECHNICAL_SETUP_REQUIRED")
    if adding:
        position = next(
            (p for p in snapshot.positions or [] if p.ticker == security.ticker), None
        )
        levels = analysis.levels
        if (
            not position
            or not position.mark
            or not levels
            or not dec(levels.lower) <= position.mark <= dec(levels.upper)
            or analysis.technical_rating not in {"BUY", "STRONG_BUY"}
            or (position.stop and position.mark <= position.stop)
        ):
            blockers.append("ADD_TECHNICAL_CONFIRMATION_REQUIRED")
    if blockers:
        return {"shares": None, "executable": False, "blockers": blockers}
    levels = analysis.levels
    candidate = Candidate(
        ticker=security.ticker,
        entry=dec(levels.upper),
        stop=dec(levels.stop),
        target=dec(levels.targets[1]),
        average_turnover=round(dec(analysis.mean_volume) * dec(analysis.price), 6)
        if analysis.mean_volume is not None
        else None,
    )
    return calculate_size(candidate, snapshot, sectors, policy, source, status, now=as_of)


@router.post("/review")
async def review(request: RiskReviewRequest, db: DB):
    brokerage = await portfolio() if request.source == "THNDR" else None

    def evaluate():
        securities = {s.ticker: s for s in db.scalars(select(EGXSecurity))}
        sectors = {
            ticker: s.sector
            for ticker, s in securities.items()
            if s.sector and s.sector.lower() not in {"unknown", "غير محدد"}
        }
        snapshot = (
            brokerage_snapshot(brokerage, securities)
            if brokerage is not None
            else request.manual or PortfolioSnapshot()
        )
        policy = load_policy(db)
        summary = summarize(snapshot, sectors, policy, request.source)
        sizing = None
        scenario = None

        def sizing_for(ticker, adding=False):
            security = securities.get(ticker)
            if not security:
                raise HTTPException(404, "UNKNOWN_SYMBOL")
            analysis = build_analysis(
                db,
                security,
                AnalysisRequest(ticker=ticker, explain=False),
                for_risk_review=True,
            )
            return size_from_analysis(
                db,
                security,
                analysis,
                snapshot,
                sectors,
                policy,
                request.source,
                adding=adding,
            )

        if request.candidate_ticker:
            existing = any(
                p.ticker == request.candidate_ticker for p in snapshot.positions or []
            )
            sizing = sizing_for(request.candidate_ticker, adding=existing)
        if request.scenario:
            position = next(
                (
                    p
                    for p in snapshot.positions or []
                    if p.ticker == request.scenario.ticker
                ),
                None,
            )
            if not position:
                raise HTTPException(422, "POSITION_NOT_AVAILABLE")
            proposed = (
                sizing_for(position.ticker, adding=True)
                if request.scenario.action == "ADD_TO_POSITION"
                else None
            )
            scenario = review_position(
                position,
                request.scenario,
                snapshot,
                {**summary, "candidate_sector": sectors.get(position.ticker)},
                policy,
                proposed,
            )
        return {
            "policy": policy,
            "portfolio": summary,
            "sizing": sizing,
            "scenario": scenario,
        }

    return await run_in_threadpool(evaluate)
