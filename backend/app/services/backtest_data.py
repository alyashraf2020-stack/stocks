"""Owner-attested, immutable data imports for execution and reproducible research."""

from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.models.backtest_run import SimulationDataset
from app.models.security import EGXSecurity
from app.schemas.backtesting import DatasetUpload
from app.services.scanner_calendar import CAIRO, COVERAGE, hours
from app.services.scanner_repository import digest
from app.services.validator import CandleValidator

WARMUP = 200


def sessions(start, end):
    if not COVERAGE[0] <= start <= end <= COVERAGE[1]:
        return []
    return [
        day
        for i in range((end - start).days + 1)
        if isinstance(hours(day := start + timedelta(days=i)), tuple)
    ]


def at(day, end=False):
    return datetime.combine(day, hours(day)[int(end)], CAIRO)


def after(day, count=1):
    ahead = sessions(day + timedelta(days=1), COVERAGE[1])
    return ahead[count - 1] if len(ahead) >= count else None


def previous(day):
    days = sessions(COVERAGE[0], day - timedelta(days=1))
    return days[-1] if days else None


def analyst_bar(ticker, bar, source):
    return {
        "ticker": ticker,
        "session_date": bar.day.isoformat(),
        **{
            f: float(getattr(bar, f))
            for f in ("open", "high", "low", "close", "volume")
        },
        "actual_provider": source,
        "validation_status": "VALID",
    }


def validate_import(db, data, now):
    if (
        not sessions(data.first_session, data.last_session)
        or data.listed_on > data.first_session
    ):
        raise ValueError("CALENDAR_OR_LISTING_COVERAGE_REQUIRED")
    if data.delisted_on and data.delisted_on <= data.listed_on:
        raise ValueError("INVALID_DELISTING_DATE")
    if data.kind == "EQUITY":
        master = db.get(EGXSecurity, data.ticker)
        if not master or not master.isin or master.isin != data.isin:
            raise ValueError("INSTRUMENT_IDENTITY_UNVERIFIED")
        if data.basis != "UNADJUSTED":
            raise ValueError("UNADJUSTED_EXECUTION_PRICES_REQUIRED")
    elif data.basis != "INDEX_LEVEL" or data.actions:
        raise ValueError("INVALID_INDEX_SERIES")
    calendar = set(sessions(data.first_session, data.last_session))
    action_days = {action.day for action in data.actions}
    halted = set(data.suspended)
    if (
        len(action_days) != len(data.actions)
        or len(halted) != len(data.suspended)
        or not (action_days | halted) <= calendar
        or any(
            action.announced_at > at(action.day) or action.announced_at > now
            for action in data.actions
        )
    ):
        raise ValueError("INVALID_POINT_IN_TIME_EVENT")
    seen = set()
    for bar in data.bars:
        if (
            bar.day not in calendar
            or bar.day in seen
            or bar.day in halted
            or (data.delisted_on and bar.day >= data.delisted_on)
            or not at(bar.day, True) <= bar.available_at <= now
            or bar.available_at.astimezone(CAIRO).date() != bar.day
        ):
            raise ValueError("INVALID_SESSION_OR_AVAILABLE_TIMESTAMP")
        if data.kind == "EQUITY":
            if (
                not bar.tick
                or not bar.lower_limit
                or not bar.upper_limit
                or bar.lower_limit >= bar.upper_limit
                or not bar.lower_limit <= bar.low <= bar.high <= bar.upper_limit
                or any(
                    level % bar.tick
                    for level in (bar.open, bar.high, bar.low, bar.close)
                )
            ):
                raise ValueError("VERIFIED_TICK_AND_DAILY_BOUNDS_REQUIRED")
            if (
                CandleValidator.validate_bar(
                    analyst_bar(data.ticker, bar, data.source)
                )["open_status"]
                != "RAW_OPEN"
            ):
                raise ValueError("INVALID_PROVIDER_OHLC")
        seen.add(bar.day)


def import_dataset(db, data, now):
    validate_import(db, data, now)
    data = data.model_copy(
        update={
            "bars": sorted(data.bars, key=lambda bar: bar.day),
            "actions": sorted(data.actions, key=lambda action: action.day),
            "suspended": sorted(data.suspended),
        }
    )
    payload = data.model_dump(mode="json")
    checksum = digest(payload)
    key = str(uuid5(NAMESPACE_URL, "egx-dataset:" + checksum))
    row = db.get(SimulationDataset, key)
    if not row:
        row = SimulationDataset(
            id=key,
            digest=checksum,
            ticker=data.ticker,
            imported=now.timestamp(),
            data=payload,
        )
        db.add(row)
    return row


def load_datasets(db, ids, *, only_equity=True):
    result = {}
    for key in ids:
        row = db.get(SimulationDataset, str(key))
        if not row or (only_equity and row.data["kind"] != "EQUITY"):
            raise ValueError("UNKNOWN_APPROVED_DATASET")
        if row.ticker in result:
            raise ValueError("DUPLICATE_INSTRUMENT_DATASET")
        result[row.ticker] = (
            row.id,
            row.digest,
            DatasetUpload.model_validate(row.data),
        )
    return result


def dataset_catalog(db):
    rows = db.scalars(
        select(SimulationDataset).order_by(SimulationDataset.imported.desc()).limit(100)
    )
    return [
        {
            "id": row.id,
            "digest": row.digest,
            "ticker": row.ticker,
            "bars": len(row.data["bars"]),
            **{
                k: row.data[k]
                for k in (
                    "kind",
                    "source",
                    "reference",
                    "basis",
                    "first_session",
                    "last_session",
                    "isin",
                )
            },
        }
        for row in rows
    ]


class History:
    def __init__(self, data):
        self.data = data
        self.bars = {x.day: x for x in data.bars}
        self.actions = {x.day: x for x in data.actions}
        self.suspended = set(data.suspended)
        self.sessions = sessions(data.first_session, data.last_session)

    def bar(self, day, known_at):
        bar = self.bars.get(day)
        return bar if bar and bar.available_at <= known_at else None

    def window(self, day, known_at):
        values = []
        for point in reversed(self.sessions):
            if point > day:
                continue
            bar = self.bar(point, known_at)
            if not bar or point in self.actions:
                break
            if bar.volume == 0:
                break
            values.append(analyst_bar(self.data.ticker, bar, self.data.source))
            if len(values) >= WARMUP:
                break
        return (
            list(reversed(values))
            if len(values) == WARMUP and values[0]["session_date"] == day.isoformat()
            else []
        )


def raw_inventory(db):
    from sqlalchemy import func

    from app.models.candle import EGXCandle

    return [
        {
            "ticker": ticker,
            "provider": provider,
            "rows": count,
            "first": first,
            "last": last,
            "execution_eligible": False,
        }
        for ticker, provider, count, first, last in db.execute(
            select(
                EGXCandle.ticker,
                EGXCandle.actual_provider,
                func.count(),
                func.min(EGXCandle.session_date),
                func.max(EGXCandle.session_date),
            )
            .group_by(EGXCandle.ticker, EGXCandle.actual_provider)
            .order_by(EGXCandle.ticker, EGXCandle.actual_provider)
        )
    ]
