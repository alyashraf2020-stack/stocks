"""Performance statistics on observed EGP equity and realized virtual exit fills."""

from collections import defaultdict
from datetime import date
from itertools import pairwise
from math import sqrt
from random import Random
from statistics import fmean, stdev


def streaks(returns):
    best = {"wins": 0, "losses": 0}
    wins = losses = 0
    for value in returns:
        wins = wins + 1 if value > 0 else 0
        losses = losses + 1 if value < 0 else 0
        best["wins"], best["losses"] = (
            max(wins, best["wins"]),
            max(losses, best["losses"]),
        )
    return best


def returns_series(curve):
    values = [
        float(item["equity"]) if item["equity"] is not None else None for item in curve
    ]
    return [
        current / previous - 1
        for previous, current in pairwise(values)
        if current is not None and previous is not None and previous > 0
    ]


def bootstrap(returns, seed):
    if len(returns) < 60:
        return None
    rng = Random(seed)
    n = len(returns)
    # Five-session contiguous blocks preserve a small amount of time dependence.
    outcomes = []
    for _ in range(400):
        draw = []
        while len(draw) < n:
            start = rng.randrange(n - 4)
            draw.extend(returns[start : start + 5])
        value = 1
        for change in draw[:n]:
            value *= 1 + change
        outcomes.append(value - 1)
    outcomes.sort()
    return {
        "seed": seed,
        "replications": 400,
        "block_sessions": 5,
        "p025": outcomes[10],
        "median": outcomes[200],
        "p975": outcomes[389],
        "interpretation": "DESCRIPTIVE_BLOCK_BOOTSTRAP_NOT_PROFIT_PROOF",
    }


def measure(curve, trades, capital, *, seed=42):
    capital = float(capital)
    exits = [t for t in trades if t["realized"] is not None]
    pnls = [float(t["realized"]) for t in exits]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p < 0]
    equity = [
        float(item["equity"]) if item["equity"] is not None else None for item in curve
    ]
    latest = equity[-1] if equity else None
    net = latest - capital if latest is not None else None
    coverage = sum(
        v is not None
        for p, v in zip(curve, equity, strict=True)
        if not p.get("baseline")
    )
    observed_periods = sum(not p.get("baseline") for p in curve)
    complete = bool(observed_periods) and coverage == observed_periods
    returns = returns_series(curve) if complete else []
    peak, drawdown, longest, running = capital, 0.0, 0, 0
    drawdown_line = []
    for item, value in zip(curve, equity, strict=True):
        if value is None:
            drawdown_line.append({"day": item["day"], "drawdown": None})
            continue
        peak = max(peak, value)
        decline = (peak - value) / peak if peak else 0
        drawdown = max(drawdown, decline)
        running = running + 1 if decline else 0
        longest = max(longest, running)
        drawdown_line.append(
            {"day": item["day"], "drawdown": decline if complete else None}
        )
    months = defaultdict(list)
    for item in curve:
        if not item.get("baseline"):
            months[item["day"][:7]].append(item)
    monthly = []
    base = capital
    for month, points in months.items():
        end = float(points[-1]["equity"]) if points[-1]["equity"] is not None else None
        value = (
            end / base - 1
            if base and end is not None and all(p["equity"] is not None for p in points)
            else None
        )
        monthly.append({"month": month, "return": value, "sessions": len(points)})
        base = end
    daily_std = stdev(returns) if len(returns) >= 20 else 0
    downside = (
        sqrt(fmean([min(value, 0) ** 2 for value in returns]))
        if len(returns) >= 20
        else 0
    )
    elapsed = (
        (
            date.fromisoformat(curve[-1]["day"]) - date.fromisoformat(curve[0]["day"])
        ).days
        if curve
        else 0
    )
    avg_equity = fmean(equity) if complete else None
    return {
        "starting_capital": capital,
        "ending_equity": latest,
        "net_profit": net,
        "gross_profit": sum(wins),
        "gross_loss": sum(losses),
        "total_return": net / capital if net is not None else None,
        "annualized_return": (latest / capital) ** (365.25 / elapsed) - 1
        if complete and elapsed >= 90 and latest > 0
        else None,
        "max_drawdown": drawdown if complete else None,
        "drawdown_duration": longest if complete else None,
        "sharpe": sqrt(252) * fmean(returns) / daily_std if daily_std else None,
        "sortino": sqrt(252) * fmean(returns) / downside if downside else None,
        "profit_factor": sum(wins) / -sum(losses) if losses else None,
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(pnls) - len(wins) - len(losses),
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "loss_rate": len(losses) / len(pnls) if pnls else None,
        "average_win": fmean(wins) if wins else None,
        "average_loss": fmean(losses) if losses else None,
        "expectancy": fmean(pnls) if pnls else None,
        "average_holding_days": fmean(t["holding_days"] for t in exits)
        if exits
        else None,
        "trades": len(pnls),
        "fills": len(trades),
        "commissions": sum(
            float(t.get("broker_commission", t["fees"])) for t in trades
        ),
        "fees": sum(float(t["fees"]) for t in trades),
        "taxes": sum(float(t["tax"]) for t in trades),
        "slippage": sum(float(t["slippage"]) for t in trades),
        "turnover": sum(float(t["notional"]) for t in trades) / avg_equity
        if avg_equity
        else None,
        "market_exposure": sum(bool(p["exposed"]) for p in curve) / observed_periods
        if observed_periods
        else None,
        "streaks": streaks(pnls),
        "valuation_coverage": {"observed": coverage, "total": observed_periods},
        "monthly": monthly,
        "drawdown_curve": drawdown_line,
        "bootstrap": bootstrap(returns, seed) if len(pnls) >= 20 else None,
    }
