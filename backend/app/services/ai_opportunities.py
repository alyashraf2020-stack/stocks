"""Deterministic ranking across symbols with a current cached EOD candle."""

from sqlalchemy import select

from app.models.candle import EGXCandle
from app.models.eodhd import EodhdCandle
from app.models.market_import import MarketImport
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import AnalysisRequest
from app.services.ai_context_builder import build_analysis
from app.services.egx_calendar import get_expected_latest_completed_session


def rank(report):
    levels = report.levels
    if (
        not levels
        or any(code == "KILL_SWITCH" or code.startswith("SHARIA_") for code in report.risk_blockers)
        or report.signal
        in {"NO_TRADE", "DATA_NOT_CURRENT", "INSUFFICIENT_DATA", "SELL", "STRONG_SELL"}
        or report.score is None
        or report.score <= 10
        or report.price <= levels.stop
    ):
        return None
    gap = (
        max(levels.lower - report.price, report.price - levels.upper, 0) / report.price
    )
    exposure = report.position.exposure_pct if report.position else None
    # Volume is a proxy. It moderates the score and cannot turn a stale symbol into a candidate.
    turnover = (report.mean_volume or 0) * report.price
    contributions = {
        "technical": round(report.score * 0.4, 2),
        "trend": round((report.trend_score or 0) * 0.15, 2),
        "liquidity_proxy": round(10 * min(turnover / 5_000_000, 1), 2),
        "reward_to_risk": round(min(levels.reward_to_risk[1], 3) * 4, 2),
        "entry_proximity": round(max(0, 20 - gap * 200), 2),
        "freshness": 5 if report.freshness == "HISTORICAL" else 0,
        "existing_exposure": -round(min((exposure or 0) * 0.4, 20), 2),
        "missing_fundamentals": -5,
    }
    return {
        "ticker": report.ticker,
        "company": report.company,
        "analysis": report,
        "score": round(sum(contributions.values()), 2),
        "components": contributions,
        "exposure_known": exposure is not None,
    }


def opportunities(db, portfolio=None):
    session = get_expected_latest_completed_session().isoformat()
    tickers = select(EGXCandle.ticker).where(EGXCandle.session_date == session).union(
        select(MarketImport.ticker).where(MarketImport.session == session),
        select(EodhdCandle.ticker).where(EodhdCandle.session_date == session),
    )
    securities = db.scalars(
        select(EGXSecurity).where(
            EGXSecurity.listing_status == "ACTIVE", EGXSecurity.ticker.in_(tickers)
        )
    ).all()
    owned = (
        {holding.ticker for holding in (portfolio.holdings or [])}
        if portfolio
        else set()
    )
    rows = []
    for security in securities:
        request = AnalysisRequest(
            ticker=security.ticker,
            explain=False,
            source="THNDR" if security.ticker in owned else "MANUAL",
        )
        row = rank(build_analysis(db, security, request, portfolio))
        if row:
            rows.append(row)
    return sorted(rows, key=lambda row: (-row["score"], row["ticker"]))[:25]
