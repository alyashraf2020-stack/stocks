"""Compare validated observations and publish alerts in the same scan transaction."""

from app.services.notification_service import emit
from app.services.scanner_repository import digest

ENTRY = {"BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT"}


def symbol_alerts(db, settings, now, row, prior, fingerprint, broker_sync=None):
    report = row.get("analysis") or {}
    previous = prior.get("analysis") or {}
    observation = row.get("observation") or {}
    flags = row.get("flags", {})
    old_flags = prior.get("flags", {})

    def send(category, severity, reason, *, threshold=False):
        obs = (
            row.get("broker_observation")
            if threshold and row.get("threshold_observation") == "BROKER"
            else observation
        )
        obs = obs or {}
        emit(
            db,
            settings,
            now,
            category,
            severity,
            {
                "ticker": row["ticker"],
                "source_timestamp": obs.get("source_timestamp"),
                "freshness": obs.get("freshness", "UNKNOWN"),
                "reason": reason,
                "_broker_sync": broker_sync,
                "_instrument": obs.get("instrument_id"),
                "_signal_expires": report.get("expires_at"),
                "_ref_session": report.get("reference_session"),
                "_fingerprint": fingerprint,
                "_scope": settings.mode,
                "limitations": [
                    "REVIEW_ONLY",
                    "NO_VERIFIED_LIVE_SESSION",
                    *report.get("risk_blockers", []),
                ],
            },
            [fingerprint, reason],
            settings.mode,
        )

    cat = row["category"]
    previous_cat = prior.get("category")
    if cat in ENTRY and cat != previous_cat:
        send({"ENTRY_WATCH": "ENTRY_ZONE"}.get(cat, cat), "OPPORTUNITY", cat)
    if cat == "UNAVAILABLE" and (
        previous_cat != cat or prior.get("reason") != row.get("reason")
    ):
        send("MARKET_DATA", "WARNING", row["reason"])
    if (
        previous
        and report.get("sharia_status")
        and report["sharia_status"] != previous.get("sharia_status")
    ):
        send("SHARIA_CHANGE", "WARNING", report["sharia_status"])
    rating = report.get("technical_rating")
    old_rating = previous.get("technical_rating")
    if (
        observation.get("freshness") == "HISTORICAL"
        and rating
        and old_rating
        and rating != old_rating
    ):
        scores = {
            "STRONG_SELL": -2,
            "SELL": -1,
            "NEUTRAL": 0,
            "BUY": 1,
            "STRONG_BUY": 2,
        }
        direction = (
            "RATING_UPGRADE"
            if scores.get(rating, 0) > scores.get(old_rating, 0)
            else "RATING_DOWNGRADE"
        )
        send("RATING_CHANGE", "INFO", f"{direction}: {old_rating} → {rating}")
    if report.get("signal") in {"SELL", "STRONG_SELL"} and report[
        "signal"
    ] != previous.get("signal"):
        send("SELL_REVIEW", "WARNING", report["decision"])
    if flags.get("stop") and flags["stop"] != old_flags.get("stop"):
        send("STOP", "WARNING", "STOP_LEVEL_OBSERVED", threshold=True)
    if flags.get("target", 0) > old_flags.get("target", 0):
        send("TARGET", "INFO", f"TARGET_{flags['target']}_OBSERVED", threshold=True)
    if (
        previous
        and flags.get("zone")
        and old_flags.get("zone")
        and flags["zone"] != old_flags["zone"]
        and (flags["zone"] != "INSIDE" or not report.get("risk_blockers"))
    ):
        send("ENTRY_ZONE", "INFO", "ZONE_" + flags["zone"])
    technical = [
        key
        for key in (
            "near_support",
            "near_resistance",
            "volume_spike",
            "volatile",
            "events",
            "pullback_watch",
            "breakout_confirmed",
        )
        if flags.get(key) and flags[key] != old_flags.get(key)
    ]
    if (
        flags.get("momentum")
        and old_flags.get("momentum")
        and flags["momentum"] != old_flags["momentum"]
    ):
        technical.append("momentum_reversal_watch")
    if technical:
        send(
            "TECHNICAL_CHANGE",
            "WARNING" if "volatile" in technical else "INFO",
            ", ".join(technical),
        )
    if (
        report.get("breakout")
        and report["breakout"] != previous.get("breakout")
        and cat in ENTRY
        and not report.get("risk_blockers")
    ):
        send("BREAKOUT", "INFO", report["breakout"])


def portfolio_alert(db, settings, now, summary, broker_sync=None):
    if not summary:
        return
    facts = {
        k: summary[k]
        for k in ("missing", "stock_breaches", "sector_breaches", "stop_breaches")
    }
    if any(facts.values()):
        emit(
            db,
            settings,
            now,
            "PORTFOLIO_RISK",
            "WARNING",
            {
                "reason": "PORTFOLIO_REVIEW_REQUIRED",
                "limitations": facts["missing"],
                "_broker_sync": broker_sync,
                "_instrument": obs.get("instrument_id"),
                "_signal_expires": report.get("expires_at"),
                "_ref_session": report.get("reference_session"),
                "_fingerprint": fingerprint,
                "_scope": settings.mode,
                "source_timestamp": summary["as_of"].isoformat()
                if summary["as_of"]
                else None,
            },
            digest(facts),
            settings.mode,
        )
