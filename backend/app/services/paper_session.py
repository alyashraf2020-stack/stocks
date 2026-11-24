"""Shared order admission, open-session reconciliation and close-only automation."""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.schemas.paper_trading import Order, OrderRequest
from app.schemas.sharia import ScreeningEvidence
from app.services.backtest_data import after, at, previous, sessions
from app.services.paper_execution import (
    apply_fill,
    corporate_action,
    expires,
    modeled_price,
    money,
    opening_order,
    quantity_cap,
    released,
    reserve,
)
from app.services.paper_portfolio import entry_size, mark, reserved
from app.services.paper_strategy import MAX_HOLD_SESSIONS, VERSION, strategy_signal
from app.services.portfolio_risk import ZERO


def key_for(*keys):
    return uuid5(NAMESPACE_URL, "/".join(map(str, keys)))


def screening_status(evidence, isin, clock):
    from app.services.sharia_screening import evaluate_screen

    if not isin:
        return "UNVERIFIED"
    # Compare server receipt time and the declared review date at the event clock.
    eligible = [
        item
        for item in evidence.get(isin, ())
        if item["recorded_at"] <= clock.timestamp()
        and item["reviewed_on"] <= clock.date().isoformat()
    ]
    latest = max(eligible, key=lambda item: item["reviewed_on"], default=None)
    return evaluate_screen(
        ScreeningEvidence.model_validate(latest["evidence"]) if latest else None,
        clock.date(),
    )["status"]


def turnover(history, reference, known_at):
    included = [day for day in history.sessions if day <= reference][-20:]
    if len(included) < 20 or included[-1] != reference:
        return None
    bars = [history.bar(day, known_at) for day in included]
    if any(bar is None or not bar.volume for bar in bars):
        return None
    return money(sum(bar.close * bar.volume for bar in bars) / 20)


def reject(order, reason):
    order.status = "CANCELLED" if order.filled else "REJECTED"
    order.reason, order.reservation = reason, ZERO
    return order


def admit(
    book,
    orders,
    request,
    day,
    created,
    history,
    profile,
    policy,
    sectors,
    sharia,
    *,
    evidence=None,
    auto_cap=None,
):
    eligible = after(day)
    # An order created after an eligible session starts cannot use that session's full bar.
    while eligible and created >= at(eligible):
        eligible = after(eligible)
    expiry = (
        after(eligible, request.expires_sessions - 1)
        if eligible and request.expires_sessions > 1
        else eligible
    )
    order = Order(
        id=str(request.key),
        request=request,
        decision_session=day,
        created=created,
        eligible=eligible or day,
        expires=expiry or eligible or day,
        evidence=evidence or {},
    )
    if not eligible:
        return reject(order, "CALENDAR_COVERAGE_REQUIRED")
    pos = book.positions.get(request.ticker)
    if request.side == "SELL":
        already_reserved = sum(
            item.remaining
            for item in orders
            if item.open
            and item.request.side == "SELL"
            and item.request.ticker == request.ticker
        )
        if not pos or request.shares > pos.shares - already_reserved:
            return reject(order, "INSUFFICIENT_UNRESERVED_SHARES")
    else:
        bar = history.bar(day, created)
        if not bar or book.cursor != day or not bar.volume or day in history.actions:
            return reject(order, "VERIFIED_CURRENT_EOD_REQUIRED")
        if any(
            o.open
            and o.request.side == "BUY"
            and o.request.ticker == request.ticker
            and (request.stop != o.request.stop or request.target != o.request.target)
            for o in orders
        ):
            return reject(order, "PENDING_ENTRY_PROTECTION_CONFLICT")
        if pos and (request.stop != pos.stop or request.target != pos.target):
            return reject(order, "ADD_REQUIRES_EXISTING_PROTECTION")
        cap = (
            request.limit
            or auto_cap
            or money(bar.close * (1 + profile.slippage_rate + profile.spread_rate / 2))
        )
        capacity, unit = entry_size(
            book,
            orders,
            request,
            cap,
            turnover(history, day, created),
            policy,
            profile,
            sectors,
            sharia,
            at(day, True),
        )
        if not capacity["shares"] or capacity["shares"] < request.shares:
            return reject(
                order,
                ",".join(capacity["blockers"]) or str(capacity.get("limiting_rule")),
            )
        order.entry_cap, order.risk_unit = cap, unit
        order.reservation = reserve(order, profile)
        if order.reservation > book.settled_cash - reserved(orders):
            return reject(order, "INSUFFICIENT_SETTLED_CASH")
        order.evidence.update(
            {
                "screening": sharia,
                "source_available_at": bar.available_at.isoformat(),
                "risk_capacity": capacity["shares"],
                "planned_risk": str(money(unit * request.shares)),
                "risk_limit": capacity.get("limiting_rule"),
                "net_reward_to_risk": str(capacity["reward_to_risk"]),
            }
        )
    order.status = "ACCEPTED"
    return order


def position_exit(
    account, ticker, day, known_at, pos, orders, *, urgent=None, reason=None
):
    if any(
        o.open
        and o.request.side == "SELL"
        and o.request.ticker == ticker
        and o.mandatory
        for o in orders
    ):
        return None
    for order in orders:
        if order.open and order.request.ticker == ticker:
            order.status, order.reason, order.reservation = (
                "CANCELLED",
                "PROTECTIVE_EXIT_PRIORITY",
                ZERO,
            )
    kind = urgent or "MARKET"
    eligible = day if urgent else after(day)
    source_day = previous(day) if urgent else day
    if not eligible or not source_day:
        return None
    request = OrderRequest(
        key=key_for(account, "exit", ticker, day, kind),
        ticker=ticker,
        side="SELL",
        kind=kind,
        shares=pos.shares,
        trigger=pos.stop
        if kind == "STOP"
        else pos.target
        if kind == "TARGET"
        else None,
    )
    order = Order(
        id=str(request.key),
        request=request,
        decision_session=source_day,
        created=(pos.protection_created or at(source_day, True))
        if urgent
        else known_at,
        eligible=eligible,
        expires=eligible,
        status="ACCEPTED",
        mandatory=bool(urgent),
        reason=reason,
        evidence={
            "strategy": pos.strategy,
            "version": VERSION,
            "protection_since": pos.opened.isoformat(),
        },
    )
    orders.append(order)
    return order


def reconcile(
    account, book, orders, histories, day, known_at, policy, profile, sectors, screen
):
    """Reconcile a session once, using only earlier marks for open risk checks."""
    if book.cursor and day <= book.cursor:
        return [], [], {}
    postings, trades = [], []
    bars = {t: source.bar(day, known_at) for t, source in histories.items()}
    for order in orders:
        expires(order, day)
    settlement = released(book, day)
    if settlement:
        postings.append(
            ("SETTLEMENT", {"amount": str(settlement), "session": day.isoformat()})
        )

    for ticker, history in histories.items():
        action = history.actions.get(day)
        if action:
            for order in orders:
                if order.open and order.request.ticker == ticker:
                    order.status, order.reason, order.reservation = (
                        "CANCELLED",
                        "CORPORATE_ACTION",
                        ZERO,
                    )
            credit = corporate_action(book, ticker, action)
            postings.append(
                (
                    "CORPORATE_ACTION",
                    {
                        "ticker": ticker,
                        "kind": action.kind,
                        "credit": str(credit),
                        "session": day.isoformat(),
                    },
                )
            )
        if (
            history.data.delisted_on
            and day >= history.data.delisted_on
            and ticker in book.positions
        ):
            raise ValueError("UNMODELED_DELISTING")

    volume_left = {t: quantity_cap(b, profile) for t, b in bars.items() if b}
    processed = set()
    for opening in (True, False):
        for ticker, pos in sorted(book.positions.items()):
            bar = bars.get(ticker)
            if not bar or not bar.volume or pos.opened >= day:
                continue
            # Opening executions precede mid-session touches. A target loses a
            # same-candle ambiguity to the stop for standing protective exits.
            stop_touched = (bar.open if opening else bar.low) <= pos.stop
            target_touched = (
                bar.open if opening else bar.high
            ) >= pos.target and bar.low > pos.stop
            if stop_touched:
                outstanding = next(
                    (
                        o
                        for o in orders
                        if o.open and o.request.ticker == ticker and o.mandatory
                    ),
                    None,
                )
                if (
                    outstanding
                    and outstanding.request.kind == "TARGET"
                    and outstanding.id not in processed
                ):
                    outstanding.status, outstanding.reason = (
                        "CANCELLED",
                        "STOP_OVERRIDES_TARGET",
                    )
                position_exit(
                    account,
                    ticker,
                    day,
                    known_at,
                    pos,
                    orders,
                    urgent="STOP",
                    reason="STOP_LOSS",
                )
            elif target_touched:
                position_exit(
                    account,
                    ticker,
                    day,
                    known_at,
                    pos,
                    orders,
                    urgent="TARGET",
                    reason="TAKE_PROFIT",
                )
        for order in sorted(
            orders, key=lambda item: (not item.mandatory, item.created, item.id)
        ):
            ticker = order.request.ticker
            bar = bars.get(ticker)
            if (
                not order.open
                or day < order.eligible
                or order.created >= at(day)
                or order.id in processed
            ):
                continue
            buy = order.request.side == "BUY"
            if buy and (
                policy.kill_switch
                or (policy.islamic_mode and screen(ticker, at(day)) != "COMPLIANT")
            ):
                reject(
                    order,
                    "KILL_SWITCH" if policy.kill_switch else "SHARIA_ENTRY_BLOCKED",
                )
                continue
            if not bar or opening_order(order, bar) != opening:
                continue
            modeled = modeled_price(order, bar, profile)
            if modeled is None:
                continue
            price, friction = modeled
            quantity = min(order.remaining, volume_left[ticker])
            pos = book.positions.get(ticker)
            if buy:
                if pos and (
                    pos.stop != order.request.stop or pos.target != order.request.target
                ):
                    reject(order, "ADD_REQUIRES_EXISTING_PROTECTION")
                    continue
                earlier = previous(day)
                capacity, _ = entry_size(
                    book,
                    [other for other in orders if other is not order],
                    order.request,
                    price,
                    turnover(histories[ticker], earlier, at(day)) if earlier else None,
                    policy,
                    profile,
                    sectors,
                    screen(ticker, at(day)),
                    at(day),
                )
                if not capacity["shares"]:
                    reject(order, ",".join(capacity["blockers"]))
                    continue
                quantity = min(quantity, capacity["shares"])
            else:
                quantity = min(quantity, pos.settled if pos else 0)
            if quantity <= 0:
                continue
            trade = apply_fill(
                book,
                order,
                bar,
                profile,
                quantity,
                price,
                friction,
                histories[ticker].data.isin,
                opening=opening,
            )
            if trade:
                volume_left[ticker] -= quantity
                processed.add(order.id)
                trades.append(trade)
    mark(book, day, bars)
    book.cursor = day
    return trades, postings, bars


def automate(
    account,
    book,
    orders,
    histories,
    day,
    known_at,
    policy,
    profile,
    sectors,
    screen,
    strategy,
    *,
    eligible_symbols=None,
    decision=None,
):
    evaluated = {}
    for ticker, history in sorted(histories.items()):
        if eligible_symbols is not None and ticker not in eligible_symbols:
            continue
        bar = history.bar(day, known_at)
        if not bar:
            evaluated[ticker] = "DATA_UNAVAILABLE"
            continue
        decide = decision or strategy_signal
        signal = decide(history.window(day, known_at), strategy)
        pos = book.positions.get(ticker)
        if pos:
            if (
                signal["reason"] == "TECHNICAL_EXIT"
                or len(sessions(pos.opened, day)) > MAX_HOLD_SESSIONS
            ) and not any(
                o.open and o.request.side == "SELL" and o.request.ticker == ticker
                for o in orders
            ):
                position_exit(
                    account,
                    ticker,
                    day,
                    known_at,
                    pos,
                    orders,
                    reason="TECHNICAL_EXIT"
                    if signal["reason"] == "TECHNICAL_EXIT"
                    else "MAX_HOLDING_PERIOD",
                )
            continue
        if signal["reason"] != "ENTRY_SETUP":
            evaluated[ticker] = signal["reason"]
            continue
        if policy.kill_switch:
            evaluated[ticker] = "KILL_SWITCH"
            continue
        key = key_for(account, strategy, ticker, day, VERSION)
        if any(
            o.id == str(key) or (o.open and o.request.ticker == ticker) for o in orders
        ):
            continue
        cap = min(signal["cap"], signal["target"] - Decimal(".000001"))
        if not signal["stop"] < cap < signal["target"]:
            evaluated[ticker] = "INVALID_ENTRY_RISK_GEOMETRY"
            continue
        request = OrderRequest(
            key=key,
            ticker=ticker,
            side="BUY",
            kind="LIMIT",
            shares=1,
            limit=cap,
            stop=signal["stop"],
            target=signal["target"],
            expires_sessions=2,
        )
        status = screen(ticker, known_at)
        capacity, _ = entry_size(
            book,
            orders,
            request,
            cap,
            signal["turnover"],
            policy,
            profile,
            sectors,
            status,
            at(day, True),
        )
        if not capacity["shares"]:
            evaluated[ticker] = ",".join(capacity["blockers"])
            continue
        request = request.model_copy(
            update={"shares": min(capacity["shares"], 100_000_000)}
        )
        evidence = {
            k: str(v) if isinstance(v, Decimal) else v for k, v in signal.items()
        }
        order = admit(
            book,
            orders,
            request,
            day,
            known_at,
            history,
            profile,
            policy,
            sectors,
            status,
            evidence={**evidence, "strategy": strategy, "version": VERSION},
        )
        orders.append(order)
        evaluated[ticker] = order.reason or order.status
    return evaluated
