import datetime
from app.services.egx_calendar import (
    is_egx_trading_day,
    get_expected_latest_completed_session,
    calculate_sessions_behind,
    get_freshness_label,
    get_freshness_display_ar,
    CAIRO_TZ
)

def test_egx_weekend_days():
    friday = datetime.date(2026, 9, 11)
    saturday = datetime.date(2026, 9, 12)
    sunday = datetime.date(2026, 9, 13)
    monday = datetime.date(2026, 9, 14)

    assert not is_egx_trading_day(friday)
    assert not is_egx_trading_day(saturday)
    assert is_egx_trading_day(sunday)
    assert is_egx_trading_day(monday)

def test_egx_holidays():
    coptic_christmas = datetime.date(2026, 1, 7)
    assert not is_egx_trading_day(coptic_christmas)


def test_october_2026_holiday_is_on_8th_not_6th():
    assert is_egx_trading_day(datetime.date(2026, 10, 6))
    assert not is_egx_trading_day(datetime.date(2026, 10, 8))
    during_session = datetime.datetime(2026, 10, 6, 12, 0, tzinfo=CAIRO_TZ)
    after_close = datetime.datetime(2026, 10, 6, 18, 0, tzinfo=CAIRO_TZ)
    assert get_expected_latest_completed_session(during_session) == datetime.date(2026, 10, 5)
    assert get_expected_latest_completed_session(after_close) == datetime.date(2026, 10, 6)
    assert calculate_sessions_behind(datetime.date(2026, 10, 5), after_close) == 1


def test_october_2026_shifted_holiday_and_weekend_keep_last_session():
    for day in (8, 9, 10):
        now = datetime.datetime(2026, 10, day, 18, 0, tzinfo=CAIRO_TZ)
        assert get_expected_latest_completed_session(now) == datetime.date(2026, 10, 7)
    before_open = datetime.datetime(2026, 10, 11, 10, 0, tzinfo=CAIRO_TZ)
    after_close = datetime.datetime(2026, 10, 11, 18, 0, tzinfo=CAIRO_TZ)
    assert get_expected_latest_completed_session(before_open) == datetime.date(2026, 10, 7)
    assert get_expected_latest_completed_session(after_close) == datetime.date(2026, 10, 11)
    assert calculate_sessions_behind(datetime.date(2026, 10, 6), after_close) == 2

def test_expected_latest_completed_session_market_open_vs_close():
    during_session = datetime.datetime(2026, 9, 9, 11, 0, 0, tzinfo=CAIRO_TZ)
    latest = get_expected_latest_completed_session(during_session)
    assert latest == datetime.date(2026, 9, 8)

    after_close = datetime.datetime(2026, 9, 9, 15, 0, 0, tzinfo=CAIRO_TZ)
    latest = get_expected_latest_completed_session(after_close)
    assert latest == datetime.date(2026, 9, 9)

def test_sessions_behind_no_weekend_penalty():
    sunday_morning = datetime.datetime(2026, 9, 13, 11, 0, 0, tzinfo=CAIRO_TZ)
    sessions_behind = calculate_sessions_behind(datetime.date(2026, 9, 10), sunday_morning)
    assert sessions_behind == 0

    sessions_behind_1 = calculate_sessions_behind(datetime.date(2026, 9, 9), sunday_morning)
    assert sessions_behind_1 == 1

def test_freshness_labels():
    # Strict Zero-Lag Freshness
    assert get_freshness_label(0) == "CURRENT"
    assert get_freshness_display_ar(0) == "محدث"
    assert get_freshness_label(1) == "OUTDATED"
    assert get_freshness_display_ar(1) == "غير محدث"
    assert get_freshness_label(2) == "OUTDATED"
    assert get_freshness_label(None) == "DATA_UNAVAILABLE"
    assert get_freshness_display_ar(None) == "غير متاح"
