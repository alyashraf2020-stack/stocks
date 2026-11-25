"""Persistence boundary for owner-only virtual accounts and orders."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.market_scan import MarketScan
from app.models.paper_account import PaperAccount
from app.models.paper_ledger import PaperLedger
from app.models.paper_order import PaperOrder
from app.models.paper_trade import PaperTrade
from app.models.security import EGXSecurity
from app.models.sharia_screening import ShariaScreening
from app.schemas.paper_trading import Book, Execution, Order
from app.services.backtest_data import History, after, load_datasets
from app.services.paper_execution import money
from app.services.paper_portfolio import mark, portfolio_view, reserved, valuation
from app.services.paper_session import (
    admit,
    automate,
    reconcile,
    reject,
    screening_status,
)
from app.services.portfolio_risk import ZERO
from app.services.risk_policy import load_policy
from app.services.scanner_calendar import calendar_at
from app.services.scanner_repository import writer

ACTIVE = ("PENDING", "ACCEPTED", "PARTIALLY_FILLED")


class PaperError(ValueError):
    pass


def current_day(now):
    day = calendar_at(now)["completed_session"]
    return date.fromisoformat(day) if day else None


def account_for(db, key, *, mutable=False):
    row = db.get(PaperAccount, str(key))
    if not row:
        raise PaperError("UNKNOWN_VIRTUAL_ACCOUNT")
    if mutable and row.archived:
        raise PaperError("VIRTUAL_ACCOUNT_ARCHIVED")
    return row


def open_orders(db, account):
    return [
        Order.model_validate(row.data)
        for row in db.scalars(
            select(PaperOrder).where(
                PaperOrder.account_id == account.id, PaperOrder.status.in_(ACTIVE)
            )
        )
    ]


def persist_orders(db, account, orders):
    for order in orders:
        db.merge(
            PaperOrder(
                account_id=account.id,
                id=order.id,
                status=order.status,
                data=order.model_dump(mode="json"),
            )
        )


def ledger(db, account, key, now, kind, payload):
    db.add(
        PaperLedger(
            account_id=account.id,
            key=key,
            created=now.timestamp(),
            kind=kind,
            data=payload,
        )
    )


def ledger_row(db, account, key):
    return db.scalar(
        select(PaperLedger).where(
            PaperLedger.account_id == account.id, PaperLedger.key == key
        )
    )


def histories_for(db, ids):
    return {
        ticker: History(data) for ticker, (_, _, data) in load_datasets(db, ids).items()
    }


def input_context(db, histories):
    sectors = {}
    isins = set()
    for ticker, history in histories.items():
        security = db.get(EGXSecurity, ticker)
        if security and security.isin == history.data.isin:
            isins.add(security.isin)
            if security.sector.lower() not in {"unknown", "غير محدد", ""}:
                sectors[ticker] = security.sector
    screenings = {}
    for row in db.scalars(
        select(ShariaScreening).where(
            ShariaScreening.isin.in_(isins), ShariaScreening.recorded_at.is_not(None)
        )
    ):
        screenings.setdefault(row.isin, []).append(
            {
                "recorded_at": row.recorded_at,
                "reviewed_on": row.reviewed_on.isoformat(),
                "evidence": row.evidence,
            }
        )
    return sectors, screenings


def screen_from(histories, records):
    return lambda ticker, clock: screening_status(
        records, histories[ticker].data.isin, clock
    )


def create(db, request, now):
    with writer(db):
        key = str(request.key)
        existing = db.get(PaperAccount, key)
        payload = request.model_dump(mode="json")
        if existing:
            if existing.initial_request != payload:
                raise PaperError("IDEMPOTENCY_KEY_CONFLICT")
            return key
        histories = histories_for(db, request.datasets)
        day = current_day(now)
        if not day or not after(day):
            raise PaperError("CALENDAR_COVERAGE_REQUIRED")
        book = Book(
            settled_cash=money(request.capital), units=request.capital, cursor=day
        )
        mark(book, day, {}, inception=True)
        row = PaperAccount(
            id=key,
            name=request.name,
            start_capital=str(book.settled_cash),
            created=now.timestamp(),
            strategy=request.strategy,
            datasets=[str(x) for x in request.datasets],
            execution=request.execution.model_dump(mode="json"),
            book=book.model_dump(mode="json"),
            initial_request=payload,
            automated=False,
        )
        db.add(row)
        db.flush()
        ledger(
            db,
            row,
            "initial",
            now,
            "INITIAL_CAPITAL",
            {"amount": row.start_capital, "tickers": sorted(histories)},
        )
        return key


def cash_change(db, key, request, now):
    with writer(db):
        row = account_for(db, key, mutable=True)
        cash_key = str(request.key)
        old = ledger_row(db, row, cash_key)
        payload = request.model_dump(mode="json")
        if old:
            if old.data.get("request") != payload:
                raise PaperError("IDEMPOTENCY_KEY_CONFLICT")
            return
        book = Book.model_validate(row.book)
        if book.cursor != current_day(now):
            raise PaperError("ACCOUNT_RECONCILIATION_REQUIRED")
        equity = valuation(book)[0]
        if equity is None or equity <= 0:
            raise PaperError("VERIFIED_VALUATION_REQUIRED")
        amount = money(request.amount)
        delta = amount if request.kind == "DEPOSIT" else -amount
        if delta < 0 and (
            amount > book.settled_cash - reserved(open_orders(db, row))
            or amount >= equity
        ):
            raise PaperError("INSUFFICIENT_SETTLED_CASH")
        if equity + delta > Decimal(1000000000):
            raise PaperError("VIRTUAL_CAPITAL_LIMIT")
        book.units += delta / (equity / book.units)
        book.settled_cash += delta
        row.book = book.model_dump(mode="json")
        ledger(
            db,
            row,
            cash_key,
            now,
            request.kind,
            {"amount": str(amount), "request": payload},
        )


def submit(db, key, request, now):
    with writer(db):
        row = account_for(db, key, mutable=True)
        old = db.get(PaperOrder, (row.id, str(request.key)))
        if old:
            if old.data["request"] != request.model_dump(mode="json"):
                raise PaperError("IDEMPOTENCY_KEY_CONFLICT")
            return old.data
        book = Book.model_validate(row.book)
        histories = histories_for(db, row.datasets)
        day = current_day(now)
        if not day:
            raise PaperError("CALENDAR_COVERAGE_REQUIRED")
        if book.cursor != day:
            raise PaperError("ACCOUNT_RECONCILIATION_REQUIRED")
        if request.ticker not in histories:
            raise PaperError("UNKNOWN_APPROVED_DATASET")
        security = db.get(EGXSecurity, request.ticker)
        if (
            not security
            or security.isin != histories[request.ticker].data.isin
            or (request.side == "BUY" and security.listing_status != "ACTIVE")
        ):
            raise PaperError("INSTRUMENT_IDENTITY_UNVERIFIED")
        sectors, evidence = input_context(db, histories)
        status = screen_from(histories, evidence)(request.ticker, now)
        pending = open_orders(db, row)
        order = admit(
            book,
            pending,
            request,
            day,
            now,
            histories[request.ticker],
            Execution.model_validate(row.execution),
            load_policy(db),
            sectors,
            status,
            evidence={"strategy": "MANUAL", "source": "OWNER"},
        )
        persist_orders(db, row, [order])
        if order.status == "REJECTED":
            notify(db, now, "PAPER_REJECTED", order.id, request.ticker, order.reason)
        return order.model_dump(mode="json")


def cancel(db, key, order_key):
    with writer(db):
        row = account_for(db, key, mutable=True)
        record = db.get(PaperOrder, (row.id, str(order_key)))
        if not record:
            raise PaperError("UNKNOWN_VIRTUAL_ORDER")
        order = Order.model_validate(record.data)
        if order.mandatory:
            raise PaperError("PROTECTIVE_EXIT_CANNOT_BE_CANCELLED")
        if order.open:
            order.status, order.reason, order.reservation = (
                "CANCELLED",
                "OWNER_CANCELLED",
                ZERO,
            )
            record.data, record.status = order.model_dump(mode="json"), order.status
        return record.data


def settings(db, key, request, now):
    with writer(db):
        row = account_for(db, key, mutable=True)
        if request.datasets is not None:
            old, new = (
                histories_for(db, row.datasets),
                histories_for(db, request.datasets),
            )
            book = Book.model_validate(row.book)
            referenced = set(book.positions) | {
                o.request.ticker for o in open_orders(db, row)
            }
            if any(
                ticker not in new or new[ticker].data.isin != old[ticker].data.isin
                for ticker in referenced
            ):
                raise PaperError("HELD_OR_PENDING_INSTRUMENT_MUST_REMAIN")
            # Preserve past input provenance for any in-flight order or position.
            for ticker in referenced:
                for day in old[ticker].bars.keys() | new[ticker].bars.keys():
                    if day <= book.cursor and old[ticker].bars.get(day) != new[
                        ticker
                    ].bars.get(day):
                        raise PaperError("PAST_OBSERVATIONS_ARE_IMMUTABLE")
            row.datasets = [str(item) for item in request.datasets]
            row.failure = None
        if request.automated and not row.automated:
            row.auto_cursor = current_day(now).isoformat() if current_day(now) else None
        row.automated, row.strategy = request.automated, request.strategy
        ledger(
            db,
            row,
            f"settings:{now.isoformat()}",
            now,
            "SETTINGS",
            request.model_dump(mode="json"),
        )


def archive(db, key, now):
    with writer(db):
        row = account_for(db, key)
        if not row.archived:
            for order in open_orders(db, row):
                order.status, order.reason, order.reservation = (
                    "CANCELLED",
                    "ACCOUNT_ARCHIVED",
                    ZERO,
                )
                persist_orders(db, row, [order])
            row.archived, row.automated = True, False
            ledger(db, row, "archive", now, "ARCHIVE", {})


def view(db, row):
    book = Book.model_validate(row.book)
    summary = portfolio_view(book, open_orders(db, row))
    return {
        "id": row.id,
        "name": row.name,
        "currency": "EGP",
        "virtual": True,
        "capital": row.start_capital,
        "archived": row.archived,
        "automated": row.automated,
        "strategy": row.strategy,
        "datasets": row.datasets,
        "execution": row.execution,
        "failure": row.failure,
        "tickers": [item for item in histories_for(db, row.datasets)],
        **summary,
    }


def checked_scan_symbols(db, day, histories, now):
    run = db.scalar(
        select(MarketScan)
        .order_by(MarketScan.job_id.desc())
        .where(
            MarketScan.summary["session"].as_string() == day.isoformat(),
            MarketScan.summary["mode"].as_string().in_(["MARKET", "WATCHLIST"]),
        )
        .limit(1)
    )
    if not run:
        return None
    selected = set()
    for row in run.results:
        obs = row.get("observation") or {}
        ticker = row["ticker"]
        if ticker not in histories:
            continue
        bar = histories[ticker].bar(day, now)
        if (
            bar
            and obs.get("instrument_id") == histories[ticker].data.isin
            and obs.get("freshness") == "HISTORICAL"
            and obs.get("validation_status") == "VALID"
            and obs.get("price") is not None
            and money(obs["price"]) == bar.close
        ):
            selected.add(ticker)
    return selected


def process(db, account_id, now):
    """One fenced transaction for the next session cut, followed by an optional scanner decision."""
    horizon = current_day(now)
    if not horizon:
        return False
    with writer(db):
        row = account_for(db, account_id)
        if row.archived or row.failure:
            return False
        book = Book.model_validate(row.book)
        day = after(book.cursor)
        pending_session = day and day <= horizon
        if not pending_session and (
            not row.automated or row.auto_cursor == horizon.isoformat()
        ):
            return False
        from app.schemas.market_import import ImportEnvironment

        if ImportEnvironment().EOD_IMPORT_PAPER_FOLLOW:
            from app.services.market_import import preferred_dataset

            newer = [preferred_dataset(db, item, book.cursor) for item in row.datasets]
            if newer != row.datasets:
                from app.services.scanner_repository import digest

                row.datasets = newer
                ledger(db, row, "dataset:" + digest(newer)[:50], now, "DATASET_UPDATE", {"datasets": newer})
        histories = histories_for(db, row.datasets)
        sectors, screenings = input_context(db, histories)
        policy, profile = load_policy(db), Execution.model_validate(row.execution)
        screen = screen_from(histories, screenings)
        orders = open_orders(db, row)
        if pending_session:
            required = set(book.positions) | {item.request.ticker for item in orders}
            if day == horizon and any(
                histories[ticker].data.last_session < day for ticker in required
            ):
                return False  # Allow the approved EOD import to catch up this session.
            for order in orders:
                security = db.get(EGXSecurity, order.request.ticker)
                if (
                    not security
                    or security.isin != histories[order.request.ticker].data.isin
                    or (
                        order.request.side == "BUY"
                        and security.listing_status != "ACTIVE"
                    )
                ):
                    reject(order, "INSTRUMENT_IDENTITY_UNVERIFIED")
            trades, postings, _ = reconcile(
                row.id,
                book,
                orders,
                histories,
                day,
                now,
                policy,
                profile,
                sectors,
                screen,
            )
            for trade in trades:
                db.add(
                    PaperTrade(
                        account_id=row.id,
                        order_id=trade["order_id"],
                        session=day.isoformat(),
                        data=trade,
                    )
                )
                ledger(db, row, f"fill:{trade['order_id']}:{day}", now, "FILL", trade)
                notify(db, now, "PAPER_FILL", [trade["order_id"], day.isoformat()], trade["ticker"],
                       trade["reason"], trade["price_known_at"])
            for index, (kind, payload) in enumerate(postings):
                ledger(db, row, f"{day}:{index}:{kind}", now, kind, payload)
            ledger(db, row, f"session:{day}", now, "SESSION", {"day": day.isoformat()})
        if (
            row.automated
            and book.cursor == horizon
            and row.auto_cursor != horizon.isoformat()
        ):
            eligible = checked_scan_symbols(db, horizon, histories, now)
            if eligible is not None:
                outcome = automate(
                    row.id,
                    book,
                    orders,
                    histories,
                    horizon,
                    now,
                    policy,
                    profile,
                    sectors,
                    screen,
                    row.strategy,
                    eligible_symbols=eligible,
                )
                row.auto_cursor = horizon.isoformat()
                ledger(db, row, f"auto:{horizon}", now, "AUTOMATION", outcome)
        row.book = book.model_dump(mode="json")
        persist_orders(db, row, orders)
    return True


def process_batch(factory, now):
    horizon = current_day(now)
    if not horizon:
        return 0
    with factory() as db:
        ids = list(
            db.scalars(
                select(PaperAccount.id)
                .where(
                    PaperAccount.archived.is_(False),
                    PaperAccount.failure.is_(None),
                    (
                        (PaperAccount.book["cursor"].as_string() < horizon.isoformat())
                        | (
                            PaperAccount.automated.is_(True)
                            & (
                                PaperAccount.auto_cursor.is_(None)
                                | (PaperAccount.auto_cursor < horizon.isoformat())
                            )
                        )
                    ),
                )
                .order_by(PaperAccount.created)
                .limit(100)
            )
        )
    count = 0
    for key in ids:
        try:
            with factory() as db:
                count += int(process(db, key, now))
        except ValueError as err:
            code = str(err)
            if code not in {
                "UNMODELED_CORPORATE_ACTION",
                "FRACTIONAL_CORPORATE_ACTION",
                "UNMODELED_DELISTING",
            }:
                code = "VIRTUAL_RECONCILIATION_FAILED"
            with factory() as db, writer(db):
                account = db.get(PaperAccount, key)
                account.failure = code
                ledger(
                    db,
                    account,
                    f"failure:{now.isoformat()}",
                    now,
                    "FAILURE",
                    {"reason": code},
                )
    return count


def notify(db, now, category, identity, ticker=None, reason=None, source_timestamp=None):
    from app.services.notification_service import emit
    from app.services.scanner_repository import load_settings

    emit(db, load_settings(db), now.timestamp(), category,
         "WARNING" if category == "PAPER_REJECTED" else "INFO",
         {"ticker": ticker, "reason": reason or category, "source_timestamp": source_timestamp,
          "freshness": "HISTORICAL" if source_timestamp else "UNKNOWN", "limitations": ["VIRTUAL_ONLY"]},
         identity, "PAPER")
