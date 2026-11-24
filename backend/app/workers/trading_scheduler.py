"""One deterministic EOD window per settings revision and completed exchange session."""

from datetime import UTC, datetime

from app.services.scanner_calendar import CAIRO, calendar_at, hours
from app.services.scanner_repository import enqueue

EOD_GRACE_SECONDS = 900


def eod_due(calendar):
    value = calendar["completed_session"]
    if value:
        day = datetime.fromisoformat(value).date()
        schedule = hours(day)
        return datetime.combine(day, schedule[1], CAIRO).timestamp() + EOD_GRACE_SECONDS
    return None


def tick(db_factory, now):
    calendar = calendar_at(datetime.fromtimestamp(now, UTC))
    due = eod_due(calendar)
    if due is not None and now >= due:
        with db_factory() as db:
            return enqueue(db, calendar, now)
    return None
