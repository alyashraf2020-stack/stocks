"""Build bounded analytical observations from approved local data sources."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, text

from app.api.v1.endpoints.integrations import portfolio
from app.api.v1.endpoints.risk import size_from_analysis
from app.integrations.openai_client import STRATEGY_VERSION, AISettings
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity
from app.models.trading_signal import TradingSignal
from app.schemas.ai_analysis import Analysis, AnalysisRequest, ManualPosition
from app.schemas.scanner import ENV
from app.services.ai_context_builder import build_analysis
from app.services.ai_decision_engine import explain
from app.services.ai_opportunities import rank
from app.services.corporate_events import CorporateEventService
from app.services import eodhd_cache
from app.services.portfolio_risk import brokerage_snapshot, dec, summarize
from app.services.risk_policy import entry_blocks, load_policy
from app.services.scanner_calendar import CAIRO, calendar_at, hours
from app.services.scanner_repository import digest, load_settings, reserve_broker_check
from app.services.sharia_filter import status_for

PORTFOLIO_MODES = {"MANUAL_PORTFOLIO", "THNDR_PORTFOLIO"}


def source_scope(settings):
    # This app has a single owner. Portfolio sources never share their observations.
    return settings.mode


def select_universe(settings, securities, holding_symbols):
    if settings.mode in PORTFOLIO_MODES:
        return sorted(holding_symbols)
    if settings.mode == "WATCHLIST":
        return settings.watchlist
    return list(
        dict.fromkeys(
            [
                *settings.watchlist,
                *sorted(
                    s.ticker
                    for s in securities.values()
                    if s.listing_status == "ACTIVE"
                ),
            ]
        )
    )


def blocked_result(ticker, reason):
    return {
        "ticker": ticker,
        "category": "UNAVAILABLE",
        "reason": reason,
        "analysis": None,
        "observation": None,
        "rank": None,
        "qualified": False,
        "executable": False,
    }


def request_for(security, settings, position, brokerage):
    if brokerage is not None:
        # Duplicate positions aren't passed to the holding advisor.
        return AnalysisRequest(ticker=security.ticker, explain=False, source="THNDR")
    snapshot = settings.manual if settings.mode == "MANUAL_PORTFOLIO" else None
    holding = None
    capital = None
    if (
        snapshot
        and position
        and position.shares
        and position.average_cost
        and position.shares == position.shares.to_integral_value()
        and position.shares <= 1_000_000_000
    ):
        holding = ManualPosition(
            shares=int(position.shares), average_price=float(position.average_cost)
        )
        capital = float(snapshot.equity) if snapshot.equity else None
    return AnalysisRequest(
        ticker=security.ticker, explain=False, position=holding, portfolio_value=capital
    )


def observations(report, pending_session, security, now, calendar):
    scheduled = hours(pending_session)
    eod_stamp = (
        datetime.combine(pending_session, scheduled[1], CAIRO).isoformat()
        if isinstance(scheduled, tuple)
        else None
    )
    stamp = report.price_timestamp.isoformat() if report.price_timestamp else None
    if stamp is None and report.reference_session:
        scheduled = hours(report.reference_session)
        if isinstance(scheduled, tuple):
            stamp = (
                eod_stamp
                if report.reference_session == pending_session
                else datetime.combine(
                    report.reference_session, scheduled[1], CAIRO
                ).isoformat()
            )
    valid = bool(report.price is not None and security.isin and stamp)
    return {
        "ticker": security.ticker,
        "instrument_id": security.isin,
        "exchange": "EGX",
        "currency": "EGP",
        "price": report.price,
        "provider": report.provider,
        "source_timestamp": stamp,
        "retrieval_timestamp": now.isoformat(),
        "freshness": report.freshness,
        "validation_status": "VALID" if valid else "UNAVAILABLE",
        "session_status": calendar["session_status"],
        "time_basis": "SESSION_CLOSE"
        if report.price_timestamp is None and stamp
        else "PROVIDER",
    }


def interactions(report, position, observation):
    price, levels = report.price, report.levels
    if (
        price is None
        or observation["validation_status"] != "VALID"
        or report.freshness
        not in {
            "HISTORICAL",
            "DELAYED",
            "REALTIME_VERIFIED",
        }
    ):
        return {}
    price = dec(price)
    stop = position.stop if position else None
    targets = levels.targets if position and levels else ()

    def near(level):
        return level is not None and abs(price - dec(level)) / price <= dec("0.02")

    return {
        "stop": f"{stop}" if stop and price <= stop else None,
        "target": max(
            (i for i, target in enumerate(targets, 1) if price >= dec(target)),
            default=0,
        ),
        "zone": (
            "BELOW"
            if price < dec(levels.lower)
            else "ABOVE"
            if price > dec(levels.upper)
            else "INSIDE"
        )
        if levels
        else None,
        "near_support": bool(levels and near(levels.support)),
        "near_resistance": bool(levels and near(levels.resistance)),
        "pullback_watch": bool(
            levels
            and price > dec(levels.upper)
            and report.trend_score
            and report.trend_score > 10
        ),
        "breakout_confirmed": report.breakout in {"ENTER_BREAKOUT", "ADD_ON_BREAKOUT"},
        "volume_spike": report.relative_volume is not None
        and report.relative_volume >= 2,
        "volatile": report.volatility_pct is not None and report.volatility_pct >= 5,
        "momentum": (
            "POSITIVE"
            if report.momentum_score > 0
            else "NEGATIVE"
            if report.momentum_score < 0
            else "NEUTRAL"
        )
        if report.momentum_score is not None
        else None,
        "events": [digest(event) for event in report.company_events],
    }


def evaluate(db, ticker, settings, context):
    now, expected, market, policy, screens, snapshot, sectors, positions, brokerage = (
        context
    )
    security = db.get(EGXSecurity, ticker)
    scope = source_scope(settings)
    if security is None or security.listing_status != "ACTIVE":
        row = blocked_result(ticker, "INACTIVE_OR_UNKNOWN_SYMBOL")
        return digest([ticker, row]), row, False
    position = positions.get(ticker)
    screen = screens.get(ticker, "UNVERIFIED")
    # Snapshot identity includes actual stored OHLCV and revisions, independent of retrieval time.
    candles = db.scalars(
        select(EGXCandle)
        .where(
            EGXCandle.ticker == ticker,
            EGXCandle.session_date <= expected.isoformat(),
        )
        .order_by(EGXCandle.session_date.desc())
        .limit(300)
    ).all()
    fresh_portfolio = bool(
        snapshot
        and snapshot.as_of
        and timedelta(0)
        <= now - snapshot.as_of
        <= timedelta(minutes=policy.max_snapshot_minutes)
    )
    fingerprint = digest(
        [
            STRATEGY_VERSION,
            market["version"],
            expected,
            market["session_status"],
            [
                security.isin,
                security.arabic_name,
                security.sector,
                security.listing_status,
            ],
            [c.to_dict() for c in candles],
            policy.model_dump(mode="json"),
            screen,
            scope,
            fresh_portfolio,
            snapshot.model_dump(mode="json") if snapshot else None,
            CorporateEventService.get_relevant_events(
                ticker, now.astimezone(CAIRO).date()
            ),
            brokerage.model_dump(mode="json") if brokerage else None,
        ]
    )
    from app.services.market_import import approved_series

    approved_version, approved_bars = approved_series(db, ticker, expected, now)
    provider_bars = eodhd_cache.history(db, ticker, expected)
    if provider_bars:
        fingerprint = digest([fingerprint, provider_bars])
    if approved_version:
        fingerprint = digest([fingerprint, approved_version])
    prior = db.get(TradingSignal, (scope, ticker))
    if prior and prior.fingerprint == fingerprint:
        return fingerprint, prior.data, True

    request = request_for(security, settings, position, brokerage)
    # EOD is always its own observation. A broker quote is never used for entry ranking.
    eod_request = (
        request.model_copy(update={"source": "MANUAL"}) if brokerage else request
    )
    report = build_analysis(
        db,
        security,
        eod_request,
        for_risk_review=True,
        scan_time=now,
        completed_session=expected,
    )
    observed = observations(report, expected, security, now, market)
    if approved_bars and report.provider == approved_bars[-1]["actual_provider"]:
        observed["source_available_at"] = approved_bars[-1].get("available_at")
    if report.provider == eodhd_cache.PROVIDER and provider_bars:
        observed["retrieval_timestamp"] = provider_bars[-1]["retrieved_at"]
    report.price_timestamp = (
        datetime.fromisoformat(observed["source_timestamp"])
        if observed["source_timestamp"]
        else None
    )
    report.market_status = (
        "UNKNOWN"
        if market["session_status"] == "PRE_MARKET"
        else market["session_status"]
    )
    report.sharia_status = screen
    thndr_observation = None
    if brokerage:
        broker_report = build_analysis(
            db,
            security,
            request,
            brokerage,
            for_risk_review=True,
            scan_time=now,
            completed_session=expected,
        )
        if broker_report.price_timestamp:
            thndr_observation = observations(
                broker_report, expected, security, now, market
            )
            original = next(
                (
                    item.quote
                    for item in brokerage.holdings or []
                    if item.ticker == ticker and item.instrument_id == security.isin
                ),
                None,
            )
            if original:
                thndr_observation["retrieval_timestamp"] = (
                    original.retrieved_at.isoformat()
                )
            thndr_observation["verified_current_session"] = False
        report.position = broker_report.position
        if thndr_observation and broker_report.freshness != "HISTORICAL":
            # Broker marks can describe observations, never trigger executable exits.
            threshold_report, threshold_obs = broker_report, thndr_observation
        else:
            threshold_report, threshold_obs = report, observed
    else:
        threshold_report, threshold_obs = report, observed
    report.suggested_shares = None
    scoring = rank(report) if report.freshness == "HISTORICAL" else None
    blockers = entry_blocks(policy, screen, advanced_supported=snapshot is not None)
    if market["session_status"] == "HALTED":
        blockers.append("MARKET_HALTED")
    if brokerage and brokerage.market_status == "HALTED":
        blockers.append("MARKET_HALTED")
    sizing = None
    if scoring and snapshot is not None and not blockers and fresh_portfolio:
        sizing = size_from_analysis(
            db,
            security,
            report,
            snapshot,
            sectors,
            policy,
            "THNDR" if brokerage else "MANUAL",
            adding=position is not None,
            screening_status=screen,
            as_of=now,
        )
        blockers.extend(sizing["blockers"])
    if scoring and snapshot is not None and not fresh_portfolio:
        blockers.append("CURRENT_SNAPSHOT")
    blocked = bool(blockers)
    if report.position and (blocked or not sizing or not sizing["shares"]):
        if report.position.action == "ADD_TO_POSITION":
            report.position.action = "WAIT"
        report.position.scenario_actions = [
            option
            for option in report.position.scenario_actions
            if option != "ADD_TO_POSITION"
        ]
        report.position.scenarios_ar = [
            line
            for line in report.position.scenarios_ar
            if not line.startswith("راجع زيادة المركز")
        ]
    report.risk_blockers = sorted(set(blockers))
    if blocked and report.signal in {"BUY", "STRONG_BUY"}:
        report.signal, report.decision = "WAIT", "PORTFOLIO_POLICY_BLOCK"
        report.explanation_ar = "قواعد المخاطر أو الفحص الحالي بتمنع اقتراح الدخول."
    flags = interactions(threshold_report, position, threshold_obs)
    unavailable = (
        report.signal in {"DATA_NOT_CURRENT", "INSUFFICIENT_DATA"} or not security.isin
    )
    if unavailable:
        category = "UNAVAILABLE"
    elif blocked and scoring:
        category = (
            "SHARIA_BLOCKED"
            if any(b.startswith("SHARIA_") for b in blockers)
            else "RISK_BLOCKED"
        )
    elif position:
        category = "HOLDING_REVIEW"
    elif scoring and report.signal in {"BUY", "STRONG_BUY"}:
        category = "BUY_REVIEW"
    elif scoring and report.breakout in {
        "ENTER_BREAKOUT",
        "WAIT_FOR_BREAKOUT",
        "WAIT_BREAKOUT_CONFIRMATION",
    }:
        category = "BREAKOUT"
    elif (
        scoring
        and report.levels
        and (
            abs(report.price - report.levels.lower) / report.price <= 0.03
            or abs(report.price - report.levels.upper) / report.price <= 0.03
            or flags.get("zone") == "INSIDE"
        )
    ):
        category = "ENTRY_WATCH"
    else:
        category = "MONITOR"
    reason = (
        ("DATA_UNAVAILABLE" if report.reference_session is None else report.decision)
        if unavailable
        else None
    )
    return (
        fingerprint,
        {
            "ticker": ticker,
            "category": category,
            "reason": reason,
            "analysis": report.model_dump(mode="json"),
            "observation": observed,
            "broker_observation": thndr_observation,
            "flags": flags,
            "threshold_observation": "BROKER"
            if threshold_obs is thndr_observation
            else "EOD",
            "rank": scoring["score"] if scoring else None,
            "rank_components": scoring["components"] if scoring else None,
            "qualified": bool(sizing and sizing["shares"] and not blocked),
            "reviewed_at": now.isoformat(),
            "executable": False,
        },
        False,
    )


def collect(db_factory, job, now):
    market = calendar_at(now)
    if market["completed_session"] != job["session"]:
        return {"error": "SESSION_CHANGED", "rows": []}
    with db_factory() as db:
        db.execute(text("BEGIN"))
        settings = load_settings(db)
        if settings.revision != job["revision"]:
            return {"error": "SETTINGS_CHANGED", "rows": []}
        policy = load_policy(db)
        securities = {s.ticker: s for s in db.scalars(select(EGXSecurity))}
        screens = {
            ticker: status_for(db, security, now.astimezone(CAIRO).date())["status"]
            for ticker, security in securities.items()
        }
        db.expunge_all()
    brokerage = None
    snapshot = settings.manual if settings.mode == "MANUAL_PORTFOLIO" else None
    if settings.mode == "THNDR_PORTFOLIO":
        with db_factory() as db:
            if not reserve_broker_check(db, now.timestamp()):
                return {"error": "THNDR_RATE_LIMITED", "rows": []}
        try:
            brokerage = asyncio.run(portfolio())
        except HTTPException as error:
            return {
                "error": "THNDR_RATE_LIMITED"
                if error.status_code == 429
                else "THNDR_UNAVAILABLE",
                "rows": [],
            }
        if brokerage.holdings is None or not brokerage.last_sync:
            return {"error": "THNDR_AUTHORIZATION_OR_SYNC_REQUIRED", "rows": []}
        snapshot = brokerage_snapshot(brokerage, securities, now=now)
        if snapshot.positions is None:
            return {"error": "THNDR_POSITIONS_UNVERIFIED", "rows": []}
    positions = {p.ticker: p for p in (snapshot.positions or [])} if snapshot else {}
    sectors = {
        ticker: s.sector
        for ticker, s in securities.items()
        if s.sector.lower() not in {"unknown", "غير محدد", ""}
    }
    universe = select_universe(settings, securities, positions)
    limit = ENV.SCANNER_MAX_SYMBOLS_PER_SCAN
    context = (
        now,
        date.fromisoformat(job["session"]),
        market,
        policy,
        screens,
        snapshot,
        sectors,
        positions,
        brokerage,
    )

    def scan(ticker):
        try:
            with db_factory() as db:
                return evaluate(db, ticker, settings, context)
        except Exception:  # noqa: BLE001 — isolate individual symbols and redact provider details.
            return (
                digest([ticker, "LOCAL_ANALYSIS_FAILED"]),
                blocked_result(ticker, "LOCAL_ANALYSIS_FAILED"),
                False,
            )

    with ThreadPoolExecutor(max_workers=ENV.SCANNER_MAX_CONCURRENCY) as pool:
        rows = list(pool.map(scan, universe[:limit]))

    config = AISettings()
    owner_secret = os.getenv("INTEGRATIONS_GATEWAY_SECRET", "").encode()
    if (
        ENV.SCANNER_AI_ENABLED
        and config.status == "CONFIGURED"
        and len(owner_secret) >= 32
    ):
        choices = sorted(
            (
                row
                for _, row, cached in rows
                if not cached
                and row["category"] in {"BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT"}
                and row["rank"] is not None
            ),
            key=lambda row: (-row["rank"], row["ticker"]),
        )[: ENV.SCANNER_MAX_AI_REQUESTS_PER_SCAN]
        for row in choices:
            report = Analysis.model_validate(row["analysis"])
            report = explain(
                report, AnalysisRequest(ticker=report.ticker), config, owner_secret
            )
            row["analysis"] = report.model_dump(mode="json")
    return {
        "policy": policy.model_dump(mode="json"),
        "rows": rows,
        "error": "SCAN_SYMBOLS_FAILED"
        if rows
        and all(row.get("reason") == "LOCAL_ANALYSIS_FAILED" for _, row, _ in rows)
        else None,
        "portfolio_risk": summarize(
            snapshot, sectors, policy, "THNDR" if brokerage else "MANUAL", now
        )
        if snapshot
        else None,
        "unscanned": universe[limit:],
        "market": market,
        "notice": "WATCHLIST_EMPTY"
        if settings.mode == "WATCHLIST" and not universe
        else None,
        "portfolio_as_of": snapshot.as_of.isoformat()
        if snapshot and snapshot.as_of
        else None,
        "broker_sync": brokerage.last_sync.isoformat() if brokerage else None,
    }
