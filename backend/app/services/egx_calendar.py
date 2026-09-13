import datetime
from typing import Optional, Set
import zoneinfo

CAIRO_TZ = zoneinfo.ZoneInfo("Africa/Cairo")

# Official Egyptian public & exchange holidays (2024 - 2026)
EGX_HOLIDAYS_SET: Set[datetime.date] = {
    # 2024
    datetime.date(2024, 1, 7),
    datetime.date(2024, 1, 25),
    datetime.date(2024, 4, 9),
    datetime.date(2024, 4, 10),
    datetime.date(2024, 4, 11),
    datetime.date(2024, 4, 25),
    datetime.date(2024, 5, 1),
    datetime.date(2024, 5, 6),
    datetime.date(2024, 6, 16),
    datetime.date(2024, 6, 17),
    datetime.date(2024, 6, 18),
    datetime.date(2024, 6, 19),
    datetime.date(2024, 6, 20),
    datetime.date(2024, 6, 30),
    datetime.date(2024, 7, 7),
    datetime.date(2024, 7, 23),
    datetime.date(2024, 9, 15),
    datetime.date(2024, 10, 6),

    # 2025
    datetime.date(2025, 1, 7),
    datetime.date(2025, 1, 25),
    datetime.date(2025, 3, 30),
    datetime.date(2025, 3, 31),
    datetime.date(2025, 4, 1),
    datetime.date(2025, 4, 21),
    datetime.date(2025, 4, 25),
    datetime.date(2025, 5, 1),
    datetime.date(2025, 6, 5),
    datetime.date(2025, 6, 6),
    datetime.date(2025, 6, 7),
    datetime.date(2025, 6, 8),
    datetime.date(2025, 6, 26),
    datetime.date(2025, 6, 30),
    datetime.date(2025, 7, 23),
    datetime.date(2025, 9, 4),
    datetime.date(2025, 10, 6),

    # 2026
    datetime.date(2026, 1, 7),
    datetime.date(2026, 1, 25),
    datetime.date(2026, 3, 20),
    datetime.date(2026, 3, 22),
    datetime.date(2026, 4, 13),
    datetime.date(2026, 4, 25),
    datetime.date(2026, 5, 1),
    datetime.date(2026, 5, 27),
    datetime.date(2026, 5, 28),
    datetime.date(2026, 6, 16),
    datetime.date(2026, 6, 30),
    datetime.date(2026, 7, 23),
    datetime.date(2026, 8, 25),
    datetime.date(2026, 10, 6),
}

def is_egx_trading_day(d: datetime.date) -> bool:
    """
    EGX trading days: Sunday (6) through Thursday (3).
    Friday (4) and Saturday (5) are weekend days in Egypt.
    """
    if d.weekday() in (4, 5):
        return False
    if d in EGX_HOLIDAYS_SET:
        return False
    return True

def get_expected_latest_completed_session(as_of: Optional[datetime.datetime] = None) -> datetime.date:
    """
    Resolves the expected latest officially completed EGX trading session as of a given datetime (Cairo time).
    EGX session closes at 14:30 Cairo time.
    During an active trading day (< 14:30 Cairo time), today's session is unfinished,
    so the latest COMPLETED session is the previous valid trading day.
    After 14:30 on a trading day, today's session is completed.
    On weekends (Friday/Saturday) or holidays, steps back to the most recent completed trading day.
    """
    if as_of is None:
        now_cairo = datetime.datetime.now(CAIRO_TZ)
    else:
        if as_of.tzinfo is None:
            now_cairo = as_of.replace(tzinfo=CAIRO_TZ)
        else:
            now_cairo = as_of.astimezone(CAIRO_TZ)

    candidate_date = now_cairo.date()
    session_close_time = datetime.time(14, 30)

    if is_egx_trading_day(candidate_date):
        if now_cairo.time() >= session_close_time:
            return candidate_date
        else:
            # Active/unfinished session today -> latest completed was previous trading day
            candidate_date -= datetime.timedelta(days=1)
    else:
        # Weekend or holiday -> step back
        candidate_date -= datetime.timedelta(days=1)

    while not is_egx_trading_day(candidate_date):
        candidate_date -= datetime.timedelta(days=1)

    return candidate_date

def calculate_sessions_behind(latest_session: Optional[datetime.date], as_of: Optional[datetime.datetime] = None) -> Optional[int]:
    """
    Calculates the exact count of completed EGX trading sessions that have elapsed
    between latest_session and the expected latest completed EGX session.
    Never penalizes weekends (Friday/Saturday) or market holidays!
    """
    if latest_session is None:
        return None
    
    expected_session = get_expected_latest_completed_session(as_of)
    if latest_session >= expected_session:
        return 0

    sessions_count = 0
    cur = latest_session + datetime.timedelta(days=1)
    while cur <= expected_session:
        if is_egx_trading_day(cur):
            sessions_count += 1
        cur += datetime.timedelta(days=1)

    return sessions_count

def get_freshness_label(sessions_behind: Optional[int]) -> str:
    """
    ZERO-SESSION-LAG POLICY:
    - sessions_behind == 0: CURRENT (محدث)
    - sessions_behind > 0: OUTDATED (غير محدث)
    - None: DATA_UNAVAILABLE (غير متاح)
    """
    if sessions_behind is None:
        return "DATA_UNAVAILABLE"
    if sessions_behind == 0:
        return "CURRENT"
    return "OUTDATED"

def get_freshness_display_ar(sessions_behind: Optional[int]) -> str:
    if sessions_behind is None:
        return "غير متاح"
    if sessions_behind == 0:
        return "محدث"
    return "غير محدث"