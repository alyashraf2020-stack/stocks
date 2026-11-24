"""Replays order decisions after their session close and fills later sessions only."""

from collections import Counter
from datetime import datetime, time
from decimal import Decimal

from app.schemas.paper_trading import Book
from app.services.backtest_data import previous, sessions
from app.services.backtest_metrics import measure
from app.services.paper_portfolio import mark
from app.services.paper_session import automate, reconcile
from app.services.paper_strategy import strategy_signal
from app.services.scanner_calendar import CAIRO


def closing_clock(day):
    return datetime.combine(day, time.max, CAIRO)


def benchmark_result(history, days):
    if not history:
        return None
    prices = [history.bar(day, closing_clock(day)) for day in days]
    if not days or any(bar is None for bar in prices):
        return {
            "ticker": history.data.ticker,
            "reason": "BENCHMARK_DATES_NOT_ALIGNED",
            "coverage": sum(bar is not None for bar in prices),
            "requested": len(days),
        }
    start = prices[0].close
    return {
        "ticker": history.data.ticker,
        "kind": history.data.kind,
        "return": float(prices[-1].close / start - 1),
        "currency": "EGP",
        "series": [
            {"day": bar.day.isoformat(), "return": float(bar.close / start - 1)}
            for bar in prices
        ],
    }


def evaluate_window(
    identifier,
    days,
    histories,
    capital,
    policy,
    profile,
    sectors,
    screen,
    strategy,
    seed,
    *,
    benchmark=None,
    progressed=None,
    decision=strategy_signal,
):
    baseline = previous(days[0])
    book = Book(settled_cash=capital, units=capital, cursor=baseline)
    if baseline:
        mark(book, baseline, {}, inception=True)
    orders, trades = [], []
    diagnostics = Counter()
    diagnostics_by_ticker = {t: Counter() for t in histories}
    coverage = {
        t: {"bars_available": 0, "warmup_ready": 0, "expected": len(days)}
        for t in histories
    }
    for index, day in enumerate(days):
        clock = closing_clock(day)
        fills, _, bars = reconcile(
            identifier,
            book,
            orders,
            histories,
            day,
            clock,
            policy,
            profile,
            sectors,
            screen,
        )
        trades.extend(fills)
        for ticker, source in histories.items():
            bar = bars[ticker]
            coverage[ticker]["bars_available"] += int(bool(bar and bar.volume))
            coverage[ticker]["warmup_ready"] += int(bool(source.window(day, clock)))
        reasons = automate(
            identifier,
            book,
            orders,
            histories,
            day,
            clock,
            policy,
            profile,
            sectors,
            screen,
            strategy,
            decision=decision,
        )
        diagnostics.update(reasons.values())
        for ticker, reason in reasons.items():
            diagnostics_by_ticker[ticker][reason] += 1
        # Terminal orders are already represented by their audit diagnostics and fills.
        orders = [item for item in orders if item.open]
        if progressed:
            progressed(index + 1, len(days))
    curve = [p for p in book.history if p["day"] >= days[0].isoformat()]
    metrics = measure(
        (
            [
                {
                    "day": baseline.isoformat(),
                    "equity": str(capital),
                    "exposed": False,
                    "baseline": True,
                }
            ]
            if baseline
            else []
        )
        + curve,
        trades,
        capital,
        seed=seed,
    )
    comparison = benchmark_result(benchmark, days)
    buy_hold = {}
    for ticker, source in histories.items():
        # Close-to-close price benchmark only, and only when no corporate action breaks comparability.
        if any(days[0] <= point <= days[-1] for point in source.actions):
            buy_hold[ticker] = {"reason": "CORPORATE_ACTION_PRICE_BASIS"}
        else:
            current = benchmark_result(source, days)
            buy_hold[ticker] = {
                key: value for key, value in current.items() if key != "series"
            }
    return {
        "start": days[0].isoformat(),
        "end": days[-1].isoformat(),
        "strategy": strategy,
        "metrics": metrics,
        "curve": curve,
        "benchmarks": {
            "cash_return": 0.0,
            "approved": comparison,
            "buy_hold": buy_hold,
        },
        "coverage": coverage,
        "diagnostics": dict(diagnostics),
        "diagnostics_by_ticker": {
            t: dict(values) for t, values in diagnostics_by_ticker.items()
        },
        "positions_open_at_end": sorted(book.positions),
        "trades": trades,
    }


def scenarios(request, days):
    for strategy in request.strategies:
        yield strategy, "FULL", days, request.execution
        if request.robustness == "SPLIT" and len(days) >= 20:
            cut = len(days) * 7 // 10
            yield strategy, "IN_SAMPLE", days[:cut], request.execution
            yield strategy, "OUT_OF_SAMPLE", days[cut:], request.execution
        elif request.robustness == "WALK_FORWARD" and len(days) >= 40:
            train = len(days) // 2
            step = max(10, (len(days) - train) // 3)
            for index, pivot in enumerate(range(train, len(days), step), 1):
                if len(days[pivot : pivot + step]) < 5:
                    break
                yield (
                    strategy,
                    f"WF_TRAIN_{index}",
                    days[max(0, pivot - train) : pivot],
                    request.execution,
                )
                yield (
                    strategy,
                    f"WF_TEST_{index}",
                    days[pivot : pivot + step],
                    request.execution,
                )
                if index >= 3:
                    break
        elif request.robustness == "STRESS":
            execution = request.execution
            for label, rate in (
                ("COST_UP_50", Decimal("1.5")),
                ("COST_DOUBLE", Decimal(2)),
            ):
                max_rate = Decimal(".2") / (
                    execution.commission_rate
                    + execution.charges_rate
                    + max(execution.buy_tax_rate, execution.sell_tax_rate)
                    or Decimal(".000001")
                )
                cost = min(rate, max_rate)
                yield (
                    strategy,
                    label,
                    days,
                    execution.model_copy(
                        update={
                            "commission_rate": execution.commission_rate * cost,
                            "charges_rate": execution.charges_rate * cost,
                            "buy_tax_rate": execution.buy_tax_rate * cost,
                            "sell_tax_rate": execution.sell_tax_rate * cost,
                            "fixed_fee": execution.fixed_fee * rate,
                            "minimum_commission": execution.minimum_commission * rate,
                            "slippage_rate": min(
                                Decimal(".2") - execution.spread_rate / 2,
                                execution.slippage_rate * rate,
                            ),
                            "participation": execution.participation / rate,
                        }
                    ),
                )


def run(configuration, progress=None):
    from app.schemas.backtesting import BacktestRequest, DatasetUpload
    from app.schemas.risk import RiskPolicy
    from app.services.backtest_data import History
    from app.services.paper_trading import screen_from

    request = BacktestRequest.model_validate(configuration["request"])
    policy = RiskPolicy.model_validate(configuration["risk"])
    days = sessions(request.start, request.end)
    histories = {
        name: History(DatasetUpload.model_validate(data))
        for name, data in configuration["data"].items()
    }
    benchmark = (
        History(DatasetUpload.model_validate(configuration["benchmark_data"]))
        if configuration["benchmark_data"]
        else None
    )
    screen = screen_from(histories, configuration["screenings"])
    if not histories or not days:
        return {
            "availability": "DATA_UNAVAILABLE",
            "scenarios": [],
            "excluded": configuration["excluded"],
            "limitation": "APPROVED_POINT_IN_TIME_DATA_REQUIRED",
        }
    experiments = list(scenarios(request, days))
    output = []
    for index, (strategy, label, window, execution) in enumerate(experiments):
        if progress:
            progress(index * 100 // len(experiments))
        tested = evaluate_window(
            f"{configuration['id']}:{strategy}:{label}",
            window,
            histories,
            request.capital,
            policy,
            execution,
            configuration["sectors"],
            screen,
            strategy,
            request.seed,
            benchmark=benchmark,
            progressed=(
                lambda current, total, slot=index: progress(
                    int((slot + current / total) * 99 / len(experiments))
                )
            )
            if progress
            else None,
        )
        tested["scenario"] = label
        tested["execution"] = execution.model_dump(mode="json")
        output.append(tested)
    observed = any(
        row["warmup_ready"]
        for outcome in output
        for row in outcome["coverage"].values()
    )
    return {
        "availability": "ANALYZED" if observed else "INSUFFICIENT_WARMUP",
        "profitability": "UNVERIFIED",
        "islamic_limitation": (
            "POINT_IN_TIME_SCREENING_MISSING_OR_INELIGIBLE"
            if policy.islamic_mode
            and any(
                screen(ticker, closing_clock(day)) == "UNVERIFIED"
                for day in days
                for ticker in histories
            )
            else None
        ),
        "universe_limitation": "CURRENT_OR_OWNER_SELECTED_UNIVERSE_SURVIVORSHIP_LIMITATION",
        "scenarios": output,
        "excluded": configuration["excluded"],
    }
