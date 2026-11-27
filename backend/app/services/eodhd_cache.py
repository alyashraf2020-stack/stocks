"""Select a coherent EODHD analysis series; never splice across providers."""

from datetime import date, datetime, timedelta, UTC

from sqlalchemy import select

from app.models.eodhd import EodhdCandle
from app.models.security import EGXSecurity
from app.services.data_provider.eodhd import PROVIDER
from app.services.scanner_calendar import hours


def contiguous(rows, expected, limit):
    from app.services.data_provider.manager import ProviderManager
    from app.services.validator import CandleValidator

    bars = []
    later = None
    for row in rows:
        day = date.fromisoformat(row.session_date)
        if day > expected or not isinstance(hours(day), tuple):
            continue
        bar = CandleValidator.validate_bar(row.bar)
        if bar["validation_status"] != "VALID" or not bar["volume"]:
            if bars:
                break
            continue
        if later is not None:
            cursor = later - timedelta(days=1)
            while cursor > day and not isinstance(hours(cursor), tuple):
                cursor -= timedelta(days=1)
            if cursor != day:
                break
            if ProviderManager._is_large_close_jump(bar["close"], bars[-1]):
                if len(bars) > 1:
                    break
                bars.clear()  # Quarantine an uncorroborated close at the tail.
        bars.append(
            {
                **bar,
                "retrieved_at": datetime.fromtimestamp(row.fetched, UTC).isoformat(),
            }
        )
        later = day
        if len(bars) >= limit:
            break
    return list(reversed(bars))


def history(db, ticker, expected, limit=250):
    return contiguous(
        db.scalars(
            select(EodhdCandle)
            .join(
                EGXSecurity,
                (EGXSecurity.ticker == EodhdCandle.ticker)
                & (EGXSecurity.isin == EodhdCandle.isin),
            )
            .where(
                EodhdCandle.ticker == ticker,
                EodhdCandle.session_date <= expected.isoformat(),
            )
            .order_by(EodhdCandle.session_date.desc())
            .limit(limit + 1)
        ),
        expected,
        limit,
    )


def prefer(candidate, existing):
    if not candidate:
        return False
    if not existing:
        return True
    newer = candidate[-1]["session_date"] > existing[-1]["session_date"]
    equal = candidate[-1]["session_date"] == existing[-1]["session_date"]
    return newer or (
        equal and (len(candidate) >= 50 or len(candidate) >= len(existing))
    )


def display_freshness(provider, behind, fallback):
    if provider != PROVIDER:
        return fallback
    return "إغلاق يومي متحقّق" if behind == 0 else "إغلاق يومي قديم"
