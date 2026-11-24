from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal as D
from uuid import uuid4

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models.market_scan import MarketScan
from app.models.paper_account import PaperAccount
from app.models.paper_ledger import PaperLedger
from app.models.paper_trade import PaperTrade
from app.models.security import EGXSecurity
from app.schemas.backtesting import Action, BacktestRequest, DailyBar, DatasetUpload
from app.schemas.paper_trading import (
    AccountControl,
    AccountCreate,
    Book,
    CashRequest,
    Execution,
    Order,
    OrderRequest,
    Position,
)
from app.schemas.risk import RiskPolicy
from app.services import backtesting, paper_session, paper_trading
from app.services.backtest_data import (
    History,
    after,
    at,
    import_dataset,
    sessions,
)
from app.services.backtest_engine import (
    benchmark_result,
    closing_clock,
    evaluate_window,
    scenarios,
)
from app.services.backtest_metrics import measure
from app.services.paper_execution import (
    apply_fill,
    corporate_action,
    modeled_price,
    quantity_cap,
    released,
)
from app.services.paper_portfolio import valuation
from app.services.paper_session import reconcile, screening_status
from app.services.risk_policy import save_policy
from app.services.scanner_repository import writer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

DAY = date(2026, 11, 17)
DAY2, DAY3, DAY4 = (after(DAY, i) for i in (1, 2, 3))
NOW = closing_clock(DAY)
MASTER = "EGS60201C018"


def execution(**overrides):
    return Execution(
        **{
            "commission_rate": ".001",
            "buy_tax_rate": ".001",
            "sell_tax_rate": ".002",
            "charges_rate": ".001",
            "fixed_fee": "1",
            "minimum_commission": ".5",
            "slippage_rate": ".005",
            "spread_rate": ".002",
            "participation": ".05",
            "assumptions_source": "Synthetic test assumptions",
            **overrides,
        }
    )


def bar(day, **changes):
    return DailyBar(
        **{
            "day": day,
            "available_at": at(day, True) + timedelta(minutes=2),
            "open": "99",
            "high": "102",
            "low": "98",
            "close": "100",
            "volume": 50_000,
            "tick": ".01",
            "lower_limit": "80",
            "upper_limit": "125",
            **changes,
        }
    )


def data(changes=None, **overrides):
    changes = changes or {}
    start, end = date(2026, 1, 4), after(DAY, 4)
    return DatasetUpload(
        **{
            "ticker": "COMI",
            "isin": MASTER,
            "kind": "EQUITY",
            "basis": "UNADJUSTED",
            "currency": "EGP",
            "exchange": "EGX",
            "source": "Synthetic offline unit test",
            "reference": "fixture-local",
            "rights_confirmed": True,
            "actions_reviewed": True,
            "listed_on": start,
            "first_session": start,
            "last_session": end,
            "bars": [bar(day, **changes.get(day, {})) for day in sessions(start, end)],
            **overrides,
        }
    )


@pytest.fixture
def database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'virtual.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        db.add(
            EGXSecurity(
                ticker="COMI",
                isin=MASTER,
                arabic_name="شركة اختبار",
                english_name="Test Stock",
                sector="Banks",
                listing_status="ACTIVE",
                source_updated_at="2026-01-01",
            )
        )
        db.commit()
    yield factory
    engine.dispose()


def approved(database, dataset=None):
    with database() as db, writer(db):
        return import_dataset(db, dataset or data(), closing_clock(after(DAY, 4))).id


def new_account(database, dataset=None):
    request = AccountCreate(
        key=uuid4(),
        name="Paper Test",
        capital=D(10000),
        execution=execution(),
        datasets=[approved(database, dataset)],
    )
    with database() as db:
        assert paper_trading.create(db, request, NOW) == str(request.key)
        assert paper_trading.create(db, request, NOW) == str(request.key)
    return str(request.key)


def buy(shares=4, **overrides):
    return OrderRequest(
        **{
            "key": uuid4(),
            "ticker": "COMI",
            "side": "BUY",
            "kind": "LIMIT",
            "limit": "100",
            "shares": shares,
            "stop": "95",
            "target": "125",
            **overrides,
        }
    )


def sell(shares=1, **overrides):
    return OrderRequest(
        **{
            "key": uuid4(),
            "ticker": "COMI",
            "side": "SELL",
            "kind": "MARKET",
            "shares": shares,
            **overrides,
        }
    )


def mandatory(request, *, eligible=DAY2, created=NOW):
    return Order(
        id=str(request.key),
        request=request,
        status="ACCEPTED",
        decision_session=DAY,
        created=created,
        eligible=eligible,
        expires=DAY4,
        entry_cap=D(100) if request.side == "BUY" else None,
        reservation=D(1000),
    )


def get_book(database, key):
    with database() as db:
        return Book.model_validate(db.get(PaperAccount, key).book)


def test_account_creation_idempotent_and_cash_withdrawal_reconciles(database):
    key = new_account(database)
    transaction = CashRequest(key=uuid4(), amount="1000", kind="DEPOSIT")
    with database() as db:
        paper_trading.cash_change(db, key, transaction, NOW)
        paper_trading.cash_change(db, key, transaction, NOW)
    with (
        database() as db,
        pytest.raises(paper_trading.PaperError, match="INSUFFICIENT_SETTLED_CASH"),
    ):
        paper_trading.cash_change(
            db, key, CashRequest(key=uuid4(), amount="12000", kind="WITHDRAWAL"), NOW
        )
    with database() as db:
        paper_trading.cash_change(
            db, key, CashRequest(key=uuid4(), amount="500", kind="WITHDRAWAL"), NOW
        )
    book = get_book(database, key)
    assert book.settled_cash == book.units == D(10500)
    with database() as db:
        assert db.scalar(select(func.count()).select_from(PaperLedger)) == 3


def test_partial_fill_same_session_no_double_fill_cost_and_t2(database):
    source = data({DAY2: {"volume": 40}})
    key = new_account(database, source)
    request = buy()
    with database() as db:
        accepted = paper_trading.submit(db, key, request, NOW)
        assert accepted["status"] == "ACCEPTED"
        assert accepted == paper_trading.submit(db, key, request, NOW)
        assert paper_trading.process(db, key, NOW) is False

    def competing(_):
        with database() as db:
            return paper_trading.process(db, key, closing_clock(DAY2))

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(competing, range(4))) == 1
    book = get_book(database, key)
    assert book.positions["COMI"].shares == 2
    assert book.positions["COMI"].settled == 0
    with database() as db:
        pending = paper_trading.open_orders(db, paper_trading.account_for(db, key))
        assert pending[0].status == "PARTIALLY_FILLED" and pending[0].remaining == 2
        trade = db.scalar(select(PaperTrade)).data
        assert trade["trade_session"] == DAY2.isoformat()
        assert D(trade["price"]) == D("99.60")
        assert D(trade["fees"]) == D("1.6992")
        assert book.settled_cash == D(10000) - D(trade["notional"]) - D(
            trade["fees"]
        ) - D(trade["tax"])
        assert book.positions["COMI"].cost == D(10000) - book.settled_cash
    with database() as db:
        assert paper_trading.process(db, key, closing_clock(DAY3))
    with database() as db:
        assert paper_trading.process(db, key, closing_clock(DAY4))
        assert db.scalar(select(func.count()).select_from(PaperTrade)) == 2
    result = get_book(database, key)
    assert (
        result.positions["COMI"].shares == 4 and result.positions["COMI"].settled == 2
    )
    assert result.positions["COMI"].cost == D(10000) - result.settled_cash
    assert valuation(result)[0] == result.settled_cash + D(400)


def test_fill_sell_cannot_spend_unsettled_cash_and_realized_cost_reconciles():
    order = mandatory(sell(2))
    pos = Position(
        isin=MASTER,
        cost=D(300),
        settled=3,
        stop=D(95),
        target=D(125),
        opened=DAY,
        strategy="EGX26",
    )
    book = Book(settled_cash=D(700), units=D(1000), positions={"COMI": pos})
    trade = apply_fill(book, order, bar(DAY2), execution(), 2, D(105), D(".25"), MASTER)
    net = D(trade["notional"]) - D(trade["fees"]) - D(trade["tax"])
    assert book.settled_cash == D(700) and book.proceeds[0].amount == net
    assert book.realized == net - D(200)
    assert book.positions["COMI"].cost == D(100)
    assert not released(book, DAY3)
    assert released(book, DAY4) == net
    assert book.settled_cash == D(700) + net


def test_limit_mid_session_needs_room_for_cost_and_does_not_exceed_price():
    order = mandatory(buy())
    small_cost = execution(
        commission_rate="0",
        buy_tax_rate="0",
        sell_tax_rate="0",
        fixed_fee="0",
        minimum_commission="0",
        charges_rate="0",
    )
    assert (
        modeled_price(
            order, bar(DAY2, open="103", high="105", low="100", close="103"), small_cost
        )
        is None
    )
    fill = modeled_price(
        order, bar(DAY2, open="103", high="105", low="99", close="103"), small_cost
    )
    assert fill and fill[0] == D(100)
    assert quantity_cap(bar(DAY2, volume=30), execution()) == 1


@pytest.mark.parametrize(
    ("low", "high", "opening", "expected_reason", "max_price"),
    [
        ("91", "124", "92", "STOP_LOSS", D(92)),  # Opening gap beyond 95
        ("94", "125", "100", "STOP_LOSS", D(95)),  # Both barriers touched
        ("98", "125", "100", "TAKE_PROFIT", D(125)),
    ],
)
def test_gap_ambiguous_stop_and_take_profit(
    low, high, opening, expected_reason, max_price
):
    profile = execution(slippage_rate=0, spread_rate=0)
    h = History(data({DAY2: {"low": low, "high": high, "open": opening}}))
    book = Book(
        cursor=DAY,
        units=D(10000),
        settled_cash=D(9900),
        marks={"COMI": D(100)},
        positions={
            "COMI": Position(
                isin=MASTER,
                cost=D(100),
                settled=1,
                stop=D(95),
                target=D(124),
                opened=DAY,
                strategy="TEST",
            )
        },
    )
    trades, _, _ = reconcile(
        "demo",
        book,
        [],
        {"COMI": h},
        DAY2,
        closing_clock(DAY2),
        RiskPolicy(),
        profile,
        {"COMI": "Banks"},
        lambda *_: "UNVERIFIED",
    )
    assert len(trades) == 1
    assert trades[0]["reason"] == expected_reason and D(trades[0]["price"]) <= max_price


def test_manual_open_exit_precedes_intraday_protection():
    h = History(data({DAY2: {"low": "94", "high": "125", "open": "100"}}))
    book = Book(
        cursor=DAY,
        units=D(10000),
        settled_cash=D(9900),
        positions={
            "COMI": Position(
                isin=MASTER,
                cost=D(100),
                settled=1,
                stop=D(95),
                target=D(124),
                opened=DAY,
                strategy="TEST",
            )
        },
    )
    trades, _, _ = reconcile(
        "demo",
        book,
        [mandatory(sell())],
        {"COMI": h},
        DAY2,
        closing_clock(DAY2),
        RiskPolicy(),
        execution(slippage_rate=0, spread_rate=0),
        {"COMI": "Banks"},
        lambda *_: "UNVERIFIED",
    )
    assert (
        len(trades) == 1
        and trades[0]["reason"] == "MANUAL"
        and D(trades[0]["price"]) == D(100)
    )


@pytest.mark.parametrize("flag", ["kill_switch", "islamic_mode"])
def test_emergency_and_sharia_revalidated_at_fill(database, flag):
    key = new_account(database)
    with database() as db:
        result = paper_trading.submit(db, key, buy(), NOW)
        assert result["status"] == "ACCEPTED"
    with database() as db:
        save_policy(db, RiskPolicy(**{flag: True}))
    with database() as db:
        assert paper_trading.process(db, key, closing_clock(DAY2))
        assert db.scalar(select(func.count()).select_from(PaperTrade)) == 0
    assert get_book(database, key).settled_cash == D(10000)


def test_manual_blocked_by_hard_caps_and_oversell(database):
    key = new_account(database)
    with database() as db:
        assert paper_trading.submit(db, key, buy(80), NOW)["status"] == "REJECTED"
        assert (
            paper_trading.submit(db, key, sell(1), NOW)["reason"]
            == "INSUFFICIENT_UNRESERVED_SHARES"
        )


def test_missing_quote_expires_no_fills(database):
    original = data()
    stripped = original.model_copy(
        update={"bars": [b for b in original.bars if b.day != DAY2]}
    )
    key = new_account(database, stripped)
    request = buy(expires_sessions=1)
    with database() as db:
        paper_trading.submit(db, key, request, NOW)
    with database() as db:
        paper_trading.process(db, key, closing_clock(DAY2))
    with database() as db:
        paper_trading.process(db, key, closing_clock(DAY3))
    with database() as db:
        from app.models.paper_order import PaperOrder

        assert db.get(PaperOrder, (key, str(request.key))).status == "EXPIRED"
        assert db.scalar(select(func.count()).select_from(PaperTrade)) == 0


def test_corporate_actions_rebase_share_count_and_credit_unsettled_dividend():
    book = Book(
        settled_cash=D(900),
        units=D(1000),
        marks={"COMI": D(100)},
        positions={
            "COMI": Position(
                isin=MASTER,
                cost=D(100),
                settled=1,
                stop=D(95),
                target=D(120),
                opened=DAY,
                strategy="TEST",
            )
        },
    )
    corporate_action(
        book, "COMI", Action(kind="SPLIT", day=DAY2, announced_at=NOW, ratio=2)
    )
    assert book.positions["COMI"].shares == 2 and book.positions["COMI"].cost == D(100)
    assert book.marks["COMI"] == D(50) and book.positions["COMI"].stop == D("47.5")
    assert corporate_action(
        book,
        "COMI",
        Action(
            kind="DIVIDEND",
            day=DAY3,
            announced_at=NOW,
            cash_per_share="2",
            payable_on=DAY4,
        ),
    ) == D(4)
    assert book.settled_cash == D(900) and valuation(book)[3] == D(4)
    assert released(book, DAY4) == D(4)


@pytest.mark.parametrize("mode", ["future", "duplicate", "limit", "identity"])
def test_import_preserves_identity_and_completed_availability(database, mode):
    dataset = data()
    first = dataset.bars[0]
    if mode == "future":
        dataset.bars[0] = first.model_copy(
            update={"available_at": NOW + timedelta(days=50)}
        )
    elif mode == "limit":
        dataset.bars[0] = first.model_copy(update={"upper_limit": D(90)})
    elif mode == "duplicate":
        dataset.bars.append(first)
    else:
        dataset.isin = "EGS000000000"
    with pytest.raises(ValueError), database() as db, writer(db):
        import_dataset(db, dataset, closing_clock(after(DAY, 4)))


def test_sharia_recorded_after_decision_never_backdated():
    now = closing_clock(DAY3)
    fake = {
        MASTER: [
            {
                "reviewed_on": DAY.isoformat(),
                "recorded_at": now.timestamp(),
                "evidence": {},
            }
        ]
    }
    assert screening_status(fake, MASTER, NOW) == "UNVERIFIED"


def test_strategy_input_is_immutable_until_next_available_session():
    h1 = History(data())
    h2 = History(
        data({DAY3: {"open": "117", "high": "122", "low": "115", "close": "120"}})
    )
    assert h1.window(DAY, NOW) == h2.window(DAY, NOW)
    assert len(h1.window(DAY, NOW)) == 200
    out = lambda values, _: (
        {
            "reason": "ENTRY_SETUP",
            "stop": D(95),
            "target": D(125),
            "cap": D(100),
            "rating": "BUY",
            "turnover": D(5_000_000),
        }
        if values
        else {"reason": "NO_DATA"}
    )
    args = [
        D(10000),
        RiskPolicy(),
        execution(),
        {"COMI": "Banks"},
        lambda *_: "UNVERIFIED",
        "EGX26",
        42,
    ]
    a = evaluate_window("test", [DAY, DAY2, DAY3], {"COMI": h1}, *args, decision=out)
    b = evaluate_window("test", [DAY, DAY2, DAY3], {"COMI": h2}, *args, decision=out)
    assert a["trades"][0] == b["trades"][0]
    assert a["trades"][0]["trade_session"] == DAY2.isoformat()


def test_metrics_and_benchmark_alignment():
    dates = [DAY, DAY2, DAY3]
    curve = [
        {"day": day.isoformat(), "equity": value, "exposed": True}
        for day, value in zip(dates, [100, 125, 100], strict=True)
    ]
    fills = [
        {
            "realized": amount,
            "holding_days": 2,
            "fees": 1,
            "tax": 1,
            "slippage": 1,
            "notional": 20,
        }
        for amount in (20, -10)
    ]
    metrics = measure(curve, fills, 100)
    assert metrics["profit_factor"] == 2 and metrics["win_rate"] == 0.5
    assert metrics["net_profit"] == 0 and metrics["max_drawdown"] == 0.2
    assert metrics["sharpe"] is None and metrics["fees"] == 2
    assert measure(curve, [], 100)["profit_factor"] is None
    assert benchmark_result(History(data()), dates)["return"] == 0
    item = data()
    item.bars = [b for b in item.bars if b.day != DAY2]
    assert (
        benchmark_result(History(item), dates)["reason"]
        == "BENCHMARK_DATES_NOT_ALIGNED"
    )


def test_walk_forward_has_disjoint_training_and_test_windows():
    days = sessions(date(2026, 8, 1), DAY)
    request = BacktestRequest(
        tickers=["COMI"],
        strategies=["EGX26"],
        start=days[0],
        end=days[-1],
        capital=10000,
        execution=execution(),
        robustness="WALK_FORWARD",
    )
    windows = {label: window for _, label, window, _ in scenarios(request, days)}
    assert windows["WF_TRAIN_1"][-1] < windows["WF_TEST_1"][0]
    assert set(windows["WF_TEST_1"]).isdisjoint(windows["WF_TEST_2"])


def test_backtest_queue_fencing_restart_and_no_fabricated_swdy(database):
    request = BacktestRequest(
        tickers=["SWDY"],
        strategies=["EGX26"],
        start=DAY,
        end=DAY3,
        capital=10000,
        execution=execution(),
    )
    clock = closing_clock(DAY3)
    with database() as db:
        key = backtesting.enqueue(db, request, clock)
        assert backtesting.enqueue(db, request, clock) == key
        _, old = backtesting.claim(db, clock.timestamp())
    with database() as db:
        at_recovery = clock.timestamp() + 31
        _, token = backtesting.claim(db, at_recovery)
        assert token != old
        assert not backtesting.finish(db, key, old, at_recovery, error="STALE")
        from app.services.backtest_engine import run

        result = run(backtesting.configuration(db, key))
        assert result["availability"] == "DATA_UNAVAILABLE" and result["excluded"] == {
            "SWDY": "DATA_UNAVAILABLE"
        }
        db.rollback()
        assert backtesting.finish(db, key, token, at_recovery, result=result)


def test_strategy_jobs_only_when_opted_in_and_scan_current(database, monkeypatch):
    key = new_account(database)
    signal = {
        "reason": "ENTRY_SETUP",
        "stop": D(95),
        "target": D(125),
        "cap": D(100),
        "turnover": D(5_000_000),
        "rating": "BUY",
    }
    monkeypatch.setattr(paper_session, "strategy_signal", lambda *_: signal)
    with database() as db:
        paper_trading.settings(
            db, key, AccountControl(automated=True, strategy="EGX26"), NOW
        )
        db.add(
            MarketScan(
                job_id=88,
                created=closing_clock(DAY2).timestamp(),
                summary={"mode": "WATCHLIST", "session": DAY2.isoformat()},
                results=[
                    {
                        "ticker": "COMI",
                        "observation": {
                            "price": 100,
                            "instrument_id": MASTER,
                            "freshness": "HISTORICAL",
                            "validation_status": "VALID",
                        },
                    }
                ],
            )
        )
        db.commit()
    with database() as db:
        paper_trading.process(db, key, closing_clock(DAY2))
        assert not paper_trading.process(db, key, closing_clock(DAY2))
        with db.begin():
            orders = paper_trading.open_orders(db, paper_trading.account_for(db, key))
            assert (
                len(orders) == 1
                and orders[0].request.side == "BUY"
                and orders[0].eligible == DAY3
            )
            assert db.scalar(select(func.count()).select_from(PaperTrade)) == 0


def test_private_owner_api(database, monkeypatch):
    owner = "test-virtual-owner-secret-with-at-least-32-characters"
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", owner)

    def bind():
        with database() as db:
            yield db

    app.dependency_overrides[get_db] = bind
    try:
        client = TestClient(app)
        assert client.get("/api/v1/paper-trading/accounts").status_code == 403
        assert client.post("/api/v1/backtesting/runs", json={}).status_code == 403
        assert (
            client.get(
                "/api/v1/backtesting/datasets", headers={"X-EGX-Gateway": owner}
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.pop(get_db)
