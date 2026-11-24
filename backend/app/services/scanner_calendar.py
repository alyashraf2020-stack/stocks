"""Versioned analytical calendar. Scheduled hours do not verify live status."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.egx_calendar import EGX_HOLIDAYS_SET

CAIRO = ZoneInfo("Africa/Cairo")
VERSION = "EGX-EOD-2026.1"
COVERAGE = (date(2026, 1, 1), date(2026, 12, 31))
SOURCE = "https://www.egx.com.eg/"
# EGX Ramadan announcement of 16 February 2026. Friday/Saturday remain closed.
RAMADAN = (date(2026, 2, 19), date(2026, 3, 18))
# Special closures/halts require a dated exchange notice before adding here.
SPECIAL: dict[date, tuple[time, time] | str] = {
    # EGX Eid al-Fitr closure through March 23 and Eid al-Adha through May 31.
    date(2026, 3, 19): "CLOSED",
    date(2026, 3, 23): "CLOSED",
    date(2026, 5, 26): "CLOSED",
    date(2026, 5, 31): "CLOSED",
}


def hours(day):
    override = SPECIAL.get(day)
    if override is not None:
        return override
    if day.weekday() in (4, 5) or day in EGX_HOLIDAYS_SET:
        return "CLOSED"
    return time(10), time(13, 30) if RAMADAN[0] <= day <= RAMADAN[1] else time(14, 30)


def calendar_at(now):
    local = now.astimezone(CAIRO)
    day = local.date()
    result = {
        "version": VERSION,
        "source": SOURCE,
        "coverage": [d.isoformat() for d in COVERAGE],
        "live_verified": False,
        "session_status": "UNKNOWN",
        "scheduled_status": "UNKNOWN",
        "completed_session": None,
        "next_close": None,
    }
    if not COVERAGE[0] <= day <= COVERAGE[1]:
        return result
    today = hours(day)
    if isinstance(today, str):
        result["session_status"] = today
        result["scheduled_status"] = today
    else:
        opening, closing = today
        clock = local.time()
        scheduled = (
            "CLOSED"
            if clock >= closing
            else "PRE_MARKET"
            if clock < opening
            else "OPEN"
        )
        result["scheduled_status"] = scheduled
        result["session_status"] = scheduled if scheduled != "OPEN" else "UNKNOWN"
    for offset in range(8):
        candidate = day - timedelta(days=offset)
        if candidate < COVERAGE[0]:
            break
        session = hours(candidate)
        if isinstance(session, tuple) and (offset or local.time() >= session[1]):
            result["completed_session"] = candidate.isoformat()
            break
    for offset in range(8):
        candidate = day + timedelta(days=offset)
        if candidate > COVERAGE[1]:
            break
        session = hours(candidate)
        if isinstance(session, tuple):
            close = datetime.combine(candidate, session[1], CAIRO)
            if close > local:
                result["next_close"] = close.timestamp()
                break
    return result
