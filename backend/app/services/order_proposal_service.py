"""Local immutable draft versions. No brokerage mutation or submission queue."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.models.order_approval import ReviewChallenge
from app.models.order_event import OrderEvent
from app.models.order_proposal import OrderProposal, TradingControl
from app.models.risk_settings import RiskSettings
from app.models.security import EGXSecurity
from app.schemas.ai_analysis import AnalysisRequest
from app.schemas.order_proposal import TradingSettings
from app.services.ai_context_builder import build_analysis
from app.services.order_validation import (
    BUY,
    account_limits,
    amount,
    estimate,
    price_within_review,
)
from app.services.portfolio_risk import brokerage_snapshot
from app.services.risk_policy import load_policy
from app.services.risk_scenarios import review_position
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_repository import digest, load_settings
from app.services.sharia_filter import status_for

ACTIVE = frozenset({"BLOCKED", "APPROVAL_REQUIRED", "LOCAL_REVIEWED"})
TRANSITIONS = {
    "DRAFT": {"BLOCKED"},
    "BLOCKED": {"APPROVAL_REQUIRED", "CANCELLED", "INVALIDATED", "EXPIRED"},
    "APPROVAL_REQUIRED": {"LOCAL_REVIEWED", "CANCELLED", "INVALIDATED", "EXPIRED"},
    "LOCAL_REVIEWED": {"CANCELLED", "INVALIDATED", "EXPIRED"},
}
TTL = 1800


class ProposalError(ValueError):
    pass


def settings(db):
    row = db.get(TradingControl, 1)
    return TradingSettings.model_validate(row.settings) if row else TradingSettings()


def set_settings(db, updated):
    old = settings(db)
    if updated.revision != old.revision:
        raise ProposalError("SETTINGS_CHANGED")
    if updated.automatic_drafts and updated.mode != "SEMI_AUTOMATIC_REVIEW":
        raise ProposalError("ENABLE_REVIEW_MODE_FIRST")
    result = updated.model_copy(update={"revision": old.revision + 1})
    db.merge(TradingControl(id=1, settings=result.model_dump(mode="json")))
    return result


def by_id(db, key):
    row = db.get(OrderProposal, str(key))
    if not row:
        raise ProposalError("UNKNOWN_DRAFT")
    return row


def event(db, row, at, kind, details=None):
    db.add(
        OrderEvent(proposal_id=row.id, kind=kind, created=at, evidence=details or {})
    )


def transition(db, row, state, now, reason=None):
    if state not in TRANSITIONS.get(row.state, set()):
        raise ProposalError("INVALID_DRAFT_STATE")
    before = row.state
    row.state = state
    if state not in ACTIVE:
        row.active_intent = None
        challenge = db.get(ReviewChallenge, row.id)
        if challenge:
            db.delete(challenge)
    event(db, row, now, state, {"previous": before, "reason": reason})


def current_context(db, security, policy, now, source):
    config = settings(db)
    screen = status_for(db, security, now.astimezone(CAIRO).date())
    market = calendar_at(now)
    # Do not hash transient clock or raw personal/brokerage contents into the URL.
    stored_policy = db.get(RiskSettings, 1)
    manual = load_settings(db).manual if source == "MANUAL" else None
    return {
        "policy": digest(
            [
                stored_policy.revision if stored_policy else 0,
                policy.model_dump(mode="json"),
            ]
        ),
        "sharia": screen["status"],
        "screen_evidence": digest(screen),
        "settings_revision": config.revision,
        "calendar": market["version"],
        "market_state": market["session_status"],
        "manual": digest(manual.model_dump(mode="json")) if manual else None,
        "session": market["completed_session"],
        "isin": security.isin,
        "listing": security.listing_status,
    }


def invalidate_if_needed(db, row, now):
    if row.state not in ACTIVE:
        return
    clock = now.timestamp()
    if row.expires <= clock:
        transition(db, row, "EXPIRED", clock, "DRAFT_EXPIRED")
        notify(db, row, clock, "DRAFT_EXPIRED", "DRAFT_EXPIRED")
        return
    security = db.get(EGXSecurity, row.ticker)
    policy = load_policy(db)
    actual = (
        current_context(db, security, policy, now, row.data["source"])
        if security
        else None
    )
    if actual != row.data["context"]:
        transition(db, row, "INVALIDATED", clock, "POLICY_MARKET_OR_IDENTITY_CHANGED")
        notify(
            db,
            row,
            clock,
            "DRAFT_BLOCKED",
            "POLICY_MARKET_OR_IDENTITY_CHANGED",
            "WARNING",
        )
        return
    if (
        row.data.get("reference_session")
        and row.data.get("reference")
        and row.data["freshness"] in {"HISTORICAL", "STALE"}
    ):
        from app.services.market_import import approved_series

        _, bars = approved_series(
            db,
            row.ticker,
            datetime.fromisoformat(row.data["reference_session"]).date(),
            now,
        )
        if bars and amount(bars[-1]["close"]) != amount(row.data["reference"]):
            transition(db, row, "INVALIDATED", clock, "MARKET_SNAPSHOT_CHANGED")
            notify(
                db,
                row,
                clock,
                "DRAFT_PRICE_CHANGED",
                "MARKET_SNAPSHOT_CHANGED",
                "WARNING",
            )


def notify(db, row, now, category, reason, severity="INFO"):
    from app.services.notification_service import emit

    ticker = row.ticker if row.data.get("source") != "THNDR" else None
    emit(
        db,
        load_settings(db),
        now,
        category,
        severity,
        {
            "ticker": ticker,
            "reason": reason,
            "freshness": row.data["freshness"],
            "source_timestamp": row.data.get("observation_at"),
            "_draft_id": row.id,
            "limitations": ["ANALYSIS_ONLY", "INDEPENDENT_THNDR_REVIEW"],
        },
        [row.id, category],
        "PROPOSALS",
    )


def draft_fields(db, security, request, now, policy, broker=None, analysis=None):
    from app.api.v1.endpoints.risk import size_from_analysis
    from app.schemas.risk import ScenarioRequest

    context = current_context(db, security, policy, now, request.source)
    securities = {s.ticker: s for s in db.scalars(select(EGXSecurity))}
    sectors = {
        s.ticker: s.sector
        for s in securities.values()
        if s.sector and s.sector.lower() not in {"unknown", "غير محدد"}
    }
    snapshot = (
        brokerage_snapshot(broker, securities, now)
        if broker
        else load_settings(db).manual
        if request.source == "MANUAL"
        else None
    )
    position = (
        next((p for p in snapshot.positions or [] if p.ticker == request.ticker), None)
        if snapshot
        else None
    )
    if analysis is None:
        analysis = build_analysis(
            db,
            security,
            AnalysisRequest(ticker=request.ticker, explain=False),
            for_risk_review=True,
            scan_time=now,
        )
    side = "BUY" if request.intent in BUY else "SELL"
    level = analysis.levels
    price = amount(analysis.price)
    if price is not None and price <= 0:
        price = None
    limit = request.limit or (amount(level.upper) if level and side == "BUY" else None)
    size = None
    scenario = None
    plan_price = limit or price
    if (
        side == "BUY"
        and snapshot
        and level
        and price
        and plan_price
        and amount(level.stop) < plan_price < amount(level.targets[1])
    ):
        conservative = analysis.model_copy(deep=True)
        conservative.levels.upper = float(max(plan_price, amount(level.upper)))
        if amount(conservative.levels.upper) < amount(level.targets[1]):
            size = size_from_analysis(
                db,
                security,
                conservative,
                snapshot,
                sectors,
                policy,
                request.source,
                adding=request.intent == "ADD",
                screening_status=context["sharia"],
                as_of=now,
            )
    quantity = request.shares
    if quantity is None and size and size.get("shares") and not size["blockers"]:
        quantity = min(size["shares"], 1_000_000)
    if (
        not quantity
        and request.intent == "FULL_EXIT"
        and position
        and position.shares
        and position.sellable_shares == position.shares
    ):
        quantity = (
            int(position.shares)
            if position.shares == int(position.shares) and position.shares <= 1_000_000
            else None
        )
    checked_request = request.model_copy(update={"shares": quantity})
    blockers = account_limits(
        checked_request, snapshot, position, policy, context["sharia"], size, plan_price
    )
    if not quantity and request.intent in {"PARTIAL_SELL", "TAKE_PROFIT"}:
        blockers.append("PARTIAL_EXIT_QUANTITY_REQUIRED")
    if (
        request.limit is not None
        and side == "BUY"
        and level
        and not amount(level.lower) <= request.limit <= amount(level.upper)
    ):
        blockers.append("LIMIT_OUTSIDE_ANALYSIS_ZONE")
    if side == "BUY" and request.shares and "SIZE_EXCEEDS_RISK_LIMIT" in blockers:
        quantity = None
    if side == "BUY" and (
        not level
        or not price
        or not (level.lower <= float(price) <= level.upper)
        or analysis.technical_rating not in {"BUY", "STRONG_BUY"}
    ):
        blockers.append("CURRENT_TECHNICAL_SETUP_REQUIRED")
    portfolio = None
    if snapshot:
        from app.services.portfolio_risk import summarize

        portfolio = summarize(snapshot, sectors, policy, request.source, now)
        if position and side == "SELL" and request.intent != "STOP_REVIEW" and quantity:
            scenario = review_position(
                position,
                ScenarioRequest(
                    ticker=request.ticker,
                    action=request.intent
                    if request.intent != "TAKE_PROFIT"
                    else "TAKE_PARTIAL_PROFIT",
                    shares=quantity,
                ),
                snapshot,
                {**portfolio, "candidate_sector": security.sector},
                policy,
            )
    costs = estimate(policy, side, plan_price, quantity)
    if (
        portfolio
        and side == "BUY"
        and costs["required_cash"] is not None
        and portfolio["available_cash"] is not None
        and costs["required_cash"] > portfolio["available_cash"]
    ):
        blockers.append("INSUFFICIENT_CASH_WITH_COSTS")
    pre_exposure = portfolio["total_exposure"] if portfolio else None
    post_exposure = None
    if pre_exposure is not None and costs["value"] is not None and not blockers:
        post_exposure = pre_exposure + costs["value"] * (1 if side == "BUY" else -1)
        if post_exposure < 0:
            post_exposure = None
    if (
        side == "BUY"
        and blockers
        or side == "SELL"
        and any(
            b.startswith(("INSUFFICIENT", "FULL_EXIT", "SELLABLE", "PARTIAL"))
            for b in blockers
        )
    ):
        quantity = None
        costs = estimate(policy, side, None, None)
    broker_quote = None
    if broker:
        from app.schemas.thndr import Quote
        from app.services.order_validation import check_price
        from app.services.quote_freshness import validate_quote

        matches = [
            h
            for h in broker.holdings or []
            if h.ticker == request.ticker and h.instrument_id == security.isin
        ]
        if len(matches) == 1 and matches[0].quote:
            base = Quote.model_validate(
                matches[0].quote.model_dump(include=set(Quote.model_fields))
            )
            checked = validate_quote(
                base, ticker=security.ticker, instrument_id=security.isin, now=now
            )
            broker_quote = {
                "price": amount(checked.price)
                if checked.validation_status != "INVALID"
                else None,
                "provider": checked.provider,
                "freshness": checked.freshness,
                "observation_at": checked.source_timestamp.isoformat()
                if checked.source_timestamp
                else None,
                "blocker": check_price(
                    base, security, calendar_at(now), now, settings(db)
                ),
            }
    observation = analysis.price_timestamp
    data = {
        "ticker": request.ticker,
        "company": security.arabic_name,
        "isin": security.isin,
        "listing": security.listing_status,
        "exchange": "EGX",
        "currency": "EGP",
        "intent": request.intent,
        "source": request.source,
        "side": side,
        "order_type": "CONDITIONAL_LIMIT" if limit else "REVIEW_ONLY",
        "requested_shares": request.shares,
        "requested_limit": request.limit,
        "shares": quantity,
        "reference": price,
        "limit": limit,
        "observation_at": observation.isoformat() if observation else None,
        "reference_session": str(analysis.reference_session)
        if analysis.reference_session
        else None,
        "provider": analysis.provider,
        "freshness": analysis.freshness,
        "costs": costs,
        "broker_quote": broker_quote,
        "held": position.shares if position else None,
        "sellable": position.sellable_shares if position else None,
        "broker_snapshot_at": broker.last_sync.isoformat()
        if broker and broker.last_sync
        else None,
        "buying_power": snapshot.buying_power if snapshot else None,
        "cash_after": (portfolio["available_cash"] - costs["required_cash"])
        if portfolio
        and costs["required_cash"] is not None
        and portfolio["available_cash"] is not None
        else None,
        "entry_zone": [level.lower, level.upper] if level else None,
        "stop": level.stop if level else None,
        "targets": list(level.targets) if level else None,
        "risk": amount(size["planned_risk"] * quantity / size["shares"])
        if quantity
        and size
        and size.get("shares")
        and size.get("planned_risk") is not None
        else None,
        "reward_to_risk": size.get("reward_to_risk") if size else None,
        "before_exposure": pre_exposure,
        "after_exposure": post_exposure,
        "sharia": context["sharia"],
        "supporting": analysis.supporting_ar,
        "opposing": analysis.opposing_ar,
        "explanation": analysis.explanation_ar,
        "ai_explanation": analysis.ai_explanation_ar,
        "scenario_blockers": sorted(
            set(blockers + (scenario or {}).get("limitations", []))
        ),
        "quantity_basis": "LOCAL_DETERMINISTIC_SCENARIO" if quantity else "UNAVAILABLE",
        "risk_reduction": scenario,
        "settlement_verified": False,
        "fees_verified": False,
        "invalidation": [
            "EXPIRY",
            "POLICY_CHANGE",
            "SHARIA_CHANGE",
            "SESSION_CHANGE",
            "PRICE_OR_COST_CHANGE",
        ],
        "context": context,
        "policy": policy.model_dump(mode="json"),
        "executable": False,
    }
    # Persist Decimal fields as strings. A float round-trip would change an exact review.
    return jsonable_encoder(data, custom_encoder={Decimal: str})


def create(
    db, request, now, *, broker=None, analysis=None, parent=None, origin="OWNER"
):
    request_hash = digest(request.model_dump(exclude={"key"}, mode="json"))
    existing = db.scalar(
        select(OrderProposal).where(OrderProposal.request_key == str(request.key))
    )
    if existing:
        if existing.request_hash != request_hash or existing.parent_id != (
            parent.id if parent else None
        ):
            raise ProposalError("IDEMPOTENCY_KEY_CONFLICT")
        return existing
    if parent and request.ticker != parent.ticker:
        raise ProposalError("REFRESH_INSTRUMENT_MISMATCH")
    if parent and parent.state == "CANCELLED":
        raise ProposalError("INVALID_DRAFT_STATE")
    if origin == "OWNER":
        created = db.scalar(
            select(func.count())
            .select_from(OrderProposal)
            .where(
                OrderProposal.created > now.timestamp() - 60,
                OrderProposal.data["origin"].as_string() == "OWNER",
            )
        )
        if created >= 20:
            raise ProposalError("DRAFT_RATE_LIMIT")
    security = db.get(EGXSecurity, request.ticker)
    if not security or not security.isin or security.listing_status != "ACTIVE":
        raise ProposalError("INSTRUMENT_IDENTITY_REQUIRED")
    policy = load_policy(db)
    data = draft_fields(db, security, request, now, policy, broker, analysis)
    data["origin"] = origin
    intent = digest(
        [
            request.ticker,
            request.intent,
            data["reference_session"] or now.astimezone(CAIRO).date(),
        ]
    )
    active = db.scalar(
        select(OrderProposal).where(OrderProposal.active_intent == intent)
    )
    if active and not parent:
        invalidate_if_needed(db, active, now)
        if active.state in ACTIVE:
            raise ProposalError("DUPLICATE_ACTIVE_INTENT")
        db.flush()
    if parent:
        if active and active.id != parent.id:
            raise ProposalError("DUPLICATE_ACTIVE_INTENT")
        prior = parent.data["reference"]
        refreshed = data["reference"]
        if (
            prior
            and refreshed
            and not price_within_review(
                data["side"], Decimal(prior), Decimal(refreshed), settings(db)
            )
        ):
            notify(
                db,
                parent,
                now.timestamp(),
                "DRAFT_PRICE_CHANGED",
                "PRICE_TOLERANCE_EXCEEDED",
                "WARNING",
            )
        if parent.state in ACTIVE:
            transition(
                db, parent, "INVALIDATED", now.timestamp(), "REPLACED_BY_NEW_VERSION"
            )
        db.flush()
    key = str(uuid4())
    version = parent.version + 1 if parent else 1
    expires = now.timestamp() + TTL
    row = OrderProposal(
        id=key,
        request_key=str(request.key),
        request_hash=request_hash,
        data=data,
        fingerprint=digest([key, version, expires, data]),
        active_intent=intent,
        state="DRAFT",
        ticker=request.ticker,
        version=version,
        parent_id=parent.id if parent else None,
        created=now.timestamp(),
        expires=expires,
    )
    db.add(row)
    db.flush()
    event(db, row, now.timestamp(), "DRAFT", {"origin": origin})
    transition(db, row, "BLOCKED", now.timestamp(), "LIVE_CAPABILITY_DISABLED")
    notify(db, row, now.timestamp(), "DRAFT_REVIEW", "LOCAL_REVIEW_REQUIRED")
    return row


def view(row):
    from app.services.order_reconciliation import status_view

    data = {k: value for k, value in row.data.items() if k not in {"policy", "context"}}
    return {
        "id": row.id,
        "state": row.state,
        "version": row.version,
        "parent_id": row.parent_id,
        "fingerprint": row.fingerprint,
        "created": row.created,
        "expires": row.expires,
        "broker": status_view(row),
        "handoff_enabled": False,
        **data,
    }


def sweep(db, now):
    rows = list(
        db.scalars(
            select(OrderProposal)
            .where(
                OrderProposal.state.in_(ACTIVE),
                OrderProposal.expires <= now.timestamp(),
            )
            .order_by(OrderProposal.expires)
            .limit(50)
        )
    )
    for row in rows:
        invalidate_if_needed(db, row, now)


def emergency_entries(db, now):
    from sqlalchemy import inspect

    if not inspect(db.connection()).has_table("order_proposals"):
        return
    rows = list(
        db.scalars(
            select(OrderProposal).where(
                OrderProposal.state.in_(ACTIVE),
                OrderProposal.data["intent"].as_string().in_(BUY),
            )
        )
    )
    for row in rows:
        transition(db, row, "INVALIDATED", now, "KILL_SWITCH")
        notify(db, row, now, "DRAFT_BLOCKED", "KILL_SWITCH", "WARNING")


def from_scan(db, job, rows, now):
    from uuid import NAMESPACE_URL, uuid5

    from app.schemas.ai_analysis import Analysis
    from app.schemas.order_proposal import DraftRequest

    config = settings(db)
    if not config.automatic_drafts or config.mode != "SEMI_AUTOMATIC_REVIEW":
        return
    if job.mode not in {"MARKET", "WATCHLIST"}:
        return  # Account holdings are accessible only through explicit owner review.
    if load_policy(db).kill_switch:
        return
    processed = 0
    for fingerprint, row, cached in rows:
        if cached or row["category"] not in {"BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT"}:
            continue
        if not row["analysis"] or row["analysis"].get("risk_blockers"):
            continue
        request = DraftRequest(
            key=uuid5(
                NAMESPACE_URL,
                f"egx-scan-draft:{row['ticker']}:{job.session}:{fingerprint}",
            ),
            ticker=row["ticker"],
            intent="BUY",
        )
        try:
            create(
                db,
                request,
                now,
                analysis=Analysis.model_validate(row["analysis"]),
                origin="SCANNER",
            )
        except ProposalError:
            continue
        processed += 1
        if processed >= 5:
            break
