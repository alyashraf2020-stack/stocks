"""Versioned, close-only strategies shared by paper automation and backtests."""

from decimal import Decimal

from app.services.breakout_entry import BreakoutEntryAdvisor
from app.services.indicators import TechnicalIndicatorEngine
from app.services.paper_execution import money
from app.services.technical_rating import TechnicalRatingEngine
from app.services.trade_plan import TradePlanEngine

VERSION = "EGX_PAPER_STRATEGY_V1"
MAX_HOLD_SESSIONS = 20
STRATEGIES = ("EGX26", "PULLBACK", "BREAKOUT", "TREND", "COMBINED")


def strategy_signal(bars, strategy):
    if len(bars) < 200:
        return {"reason": "INSUFFICIENT_WARMUP"}
    rating = TechnicalRatingEngine.calculate(bars, current=True)
    if not rating or rating["status"] != "COMPLETE":
        return {"reason": "INCOMPLETE_EGX26"}
    last = bars[-1]
    close = last["close"]
    volume = rating["relative_volume"]
    scores = {
        "rating": rating["signal"],
        "score": rating["score"],
        "trend": rating["trend_score"],
        "relative_volume": volume,
        "technical_method": rating["methodology"],
    }
    if rating["signal"] in {"SELL", "STRONG_SELL"}:
        return {"reason": "TECHNICAL_EXIT", **scores}
    if rating["signal"] not in {"BUY", "STRONG_BUY"} or not volume or volume < 0.7:
        return {"reason": "TECHNICAL_OR_VOLUME_GATE", **scores}

    enriched = TechnicalIndicatorEngine.compute_all_indicators(bars)
    try:
        plan = TradePlanEngine.calculate_trade_plan(enriched, 0)["trade_plan"] or {}
    except AssertionError:
        return {"reason": "NO_VALID_PLAN_GEOMETRY", **scores}
    inside = bool(plan.get("new_entry_allowed"))
    pullback = inside and close > bars[-2]["close"] and rating["trend_score"] > 0
    breakout = BreakoutEntryAdvisor.evaluate(close, enriched[:-1], 0)
    breaks = breakout.get("actionable") and volume >= 1.25 and rating["trend_score"] > 0
    trend = bool(
        rating["trend_score"] >= 35
        and last["close"] > enriched[-1]["sma_50"]
        and plan.get("stop_loss")
        and plan["stop_loss"] < close < (plan.get("target_1") or 0)
    )
    entries = {
        "EGX26": inside,
        "PULLBACK": pullback,
        "BREAKOUT": breaks,
        "TREND": trend,
        "COMBINED": breaks or (pullback and trend),
    }
    if not entries[strategy]:
        return {"reason": "NO_CONFIRMED_SETUP", **scores}
    chosen = breakout if strategy in {"BREAKOUT", "COMBINED"} and breaks else plan
    return {
        "reason": "ENTRY_SETUP",
        **scores,
        "stop": money(chosen["stop_loss"]),
        "target": money(chosen["target_2"]),
        "cap": money(
            close if strategy == "TREND" else max(close, chosen["entry_zone_max"])
        ),
        "turnover": money(
            sum(
                Decimal(str(b["close"])) * Decimal(str(b["volume"])) for b in bars[-20:]
            )
            / 20
        ),
    }
