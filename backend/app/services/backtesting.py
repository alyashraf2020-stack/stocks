"""Durable, deduplicated historical jobs with an expiring write fence."""

from datetime import date
from uuid import uuid4

from sqlalchemy import select

from app.models.backtest_result import BacktestResult
from app.models.backtest_run import BacktestRun, SimulationDataset
from app.models.backtest_trade import BacktestTrade
from app.schemas.sharia import METHOD
from app.services.backtest_data import History, load_datasets, sessions
from app.services.paper_execution import VERSION as EXECUTION_VERSION
from app.services.paper_strategy import VERSION as STRATEGY_VERSION
from app.services.paper_trading import current_day, input_context
from app.services.risk_policy import load_policy
from app.services.scanner_calendar import VERSION as CALENDAR_VERSION
from app.services.scanner_repository import digest, load_settings, writer

LEASE = 30
MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = 240


def enqueue(db, request, now):
    end = current_day(now)
    if end is None or request.end > end or not sessions(request.start, request.end):
        raise ValueError("COMPLETED_CALENDAR_RANGE_REQUIRED")
    with writer(db):
        approved = load_datasets(db, request.datasets)
        universe = set(request.tickers) | set(approved)
        if request.watchlist:
            universe.update(load_settings(db).watchlist)
        if not universe or len(universe) > 15:
            raise ValueError("SELECT_UP_TO_15_SYMBOLS")
        if (
            len(universe) * len(request.strategies) * (request.end - request.start).days
            > 6000
        ):
            raise ValueError("BACKTEST_SCOPE_TOO_LARGE")
        excluded = {}
        for ticker in sorted(universe - set(approved)):
            row = db.scalar(
                select(SimulationDataset)
                .where(
                    SimulationDataset.ticker == ticker,
                    SimulationDataset.data["kind"].as_string() == "EQUITY",
                )
                .order_by(SimulationDataset.imported.desc())
                .limit(1)
            )
            if row:
                approved.update(load_datasets(db, [row.id]))
            else:
                excluded[ticker] = "DATA_UNAVAILABLE"
        owner = load_policy(db)
        risk = request.risk or owner
        risk = risk.model_copy(
            update={
                "islamic_mode": owner.islamic_mode or risk.islamic_mode,
                "kill_switch": owner.kill_switch or risk.kill_switch,
            }
        )
        mark = {}
        if request.benchmark:
            mark = load_datasets(db, [request.benchmark], only_equity=False)
            if next(iter(mark.values()))[2].kind == "EQUITY":
                raise ValueError("BENCHMARK_INDEX_REQUIRED")
        sectors, evidence = input_context(
            db, {k: History(d) for k, (_, _, d) in approved.items()}
        )
        evidence = {
            key: [
                row
                for row in rows
                if date.fromisoformat(row["reviewed_on"]) <= request.end
            ]
            for key, rows in evidence.items()
        }
        from app.services.backtest_engine import closing_clock

        cutoff = closing_clock(request.end).timestamp()
        evidence = {
            key: [row for row in rows if row["recorded_at"] <= cutoff]
            for key, rows in evidence.items()
        }
        state = {
            "request": request.model_dump(mode="json"),
            "risk": risk.model_dump(mode="json"),
            "datasets": {
                k: {"id": key, "digest": checksum, "source": d.source, "basis": d.basis}
                for k, (key, checksum, d) in approved.items()
            },
            "benchmark": {
                k: {"id": key, "digest": checksum, "source": d.source}
                for k, (key, checksum, d) in mark.items()
            },
            "excluded": excluded,
            "screenings": evidence,
            "sectors": sectors,
            "methodology": {
                "strategy": STRATEGY_VERSION,
                "execution": EXECUTION_VERSION,
                "calendar": CALENDAR_VERSION,
                "screening": METHOD,
            },
        }
        key = digest(state)
        existing = db.get(BacktestRun, key)
        if existing:
            if existing.status in {"FAILED", "CANCELLED"}:
                (
                    existing.status,
                    existing.error,
                    existing.progress,
                    existing.attempts,
                ) = "PENDING", None, 0, 0
            return key
        queued_count = len(
            list(
                db.scalars(
                    select(BacktestRun.id)
                    .where(BacktestRun.status.in_(["PENDING", "RUNNING"]))
                    .limit(16)
                )
            )
        )
        if queued_count >= 16:
            raise ValueError("BACKTEST_QUEUE_FULL")
        db.add(
            BacktestRun(
                id=key, status="PENDING", queued=now.timestamp(), parameters=state
            )
        )
        return key


def claim(db, now):
    with writer(db):
        for row in db.scalars(
            select(BacktestRun).where(BacktestRun.status == "RUNNING")
        ):
            if row.lease and row.lease > now:
                return None
            row.status = "PENDING" if row.attempts < MAX_ATTEMPTS else "FAILED"
            row.error, row.token, row.lease = "LEASE_EXPIRED", None, None
        db.flush()
        row = db.scalar(
            select(BacktestRun)
            .where(BacktestRun.status == "PENDING")
            .order_by(BacktestRun.queued)
            .limit(1)
        )
        if not row:
            return None
        row.status, row.token, row.lease = "RUNNING", uuid4().hex, now + LEASE
        row.progress, row.error = 0, None
        row.attempts += 1
        return row.id, row.token


def current_lease(db, key, token, now):
    row = db.get(BacktestRun, key)
    return (
        row
        if row and row.status == "RUNNING" and row.token == token and row.lease > now
        else None
    )


def heartbeat(db, key, token, now, progress):
    with writer(db):
        row = current_lease(db, key, token, now)
        if row:
            row.lease, row.progress = now + LEASE, min(99, max(row.progress, progress))
        return bool(row)


def finish(db, key, token, now, result=None, error=None):
    with writer(db):
        row = current_lease(db, key, token, now)
        if not row:
            return False
        row.token, row.lease = None, None
        if error:
            row.status, row.error = "FAILED", error
        else:
            row.status, row.progress = "SUCCEEDED", 100
            result["configuration"] = row.parameters
            trades = []
            for scenario in result["scenarios"]:
                for trade in scenario.pop("trades"):
                    trades.append(
                        BacktestTrade(
                            result_id=key,
                            sequence=len(trades),
                            scenario=f"{scenario['strategy']}:{scenario['scenario']}",
                            data=trade,
                        )
                    )
            db.add(BacktestResult(id=key, data=result))
            db.add_all(trades)
        return True


def cancel(db, key):
    with writer(db):
        row = db.get(BacktestRun, key)
        if row and row.status in {"PENDING", "RUNNING"}:
            row.status, row.token, row.lease = "CANCELLED", None, None
        return bool(row)


def configuration(db, key):
    row = db.get(BacktestRun, key)
    data = dict(row.parameters)
    data["id"] = row.id
    data["data"] = {
        ticker: db.get(SimulationDataset, record["id"]).data
        for ticker, record in data["datasets"].items()
    }
    mark = next(iter(data["benchmark"].values()), None)
    data["benchmark_data"] = (
        db.get(SimulationDataset, mark["id"]).data if mark else None
    )
    return data
