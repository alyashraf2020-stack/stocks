"""File-only imports. No network retrieval or promotion of the raw cache."""

import csv
import io
import json
from datetime import date, datetime

from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.backtest_run import SimulationDataset
from app.models.market_import import MarketImport
from app.models.security import EGXSecurity
from app.schemas.backtesting import DailyBar, DatasetUpload
from app.schemas.market_import import ImportEnvironment
from app.services.backtest_data import (
    analyst_bar,
    import_dataset,
    sessions,
    validate_import,
)
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_repository import digest, writer
from app.services.validator import CandleValidator

REQUIRED = {"day", "available_at", "open", "high", "low", "close", "volume"}
EQUITY_REQUIRED = {"tick", "lower_limit", "upper_limit"}
OPTIONAL = {"opening_bid", "opening_ask"}
FIELDS = REQUIRED | EQUITY_REQUIRED | OPTIONAL


def read_bundle(envelope):
    if envelope.format == "JSON":
        try:
            result = json.loads(envelope.content)
        except (ValueError, RecursionError):
            raise ValueError("JSON_INVALID") from None
        if not isinstance(result, dict):
            raise ValueError("JSON_OBJECT_REQUIRED")
        return result
    if set(envelope.mapping) - FIELDS or len(set(envelope.mapping.values())) != len(
        envelope.mapping
    ):
        raise ValueError("CSV_MAPPING_INVALID")
    fields = REQUIRED | (
        EQUITY_REQUIRED if envelope.metadata.get("kind") == "EQUITY" else set()
    )
    try:
        reader = csv.DictReader(
            io.StringIO(envelope.content.lstrip("\ufeff"), newline=""), strict=True
        )
        headers = reader.fieldnames or []
        if len(headers) > 30 or len(set(headers)) != len(headers) or not headers:
            raise ValueError("CSV_HEADER_INVALID")
        mapping = {key: envelope.mapping.get(key, key) for key in FIELDS}
        if not {mapping[key] for key in fields} <= set(headers):
            raise ValueError("CSV_REQUIRED_COLUMNS_MISSING")
        if len({value for value in mapping.values() if value in headers}) != len(
            [value for value in mapping.values() if value in headers]
        ):
            raise ValueError("CSV_MAPPING_INVALID")
        data = []
        for entry in reader:
            if (
                len(data) >= 420
                or None in entry
                or any(x is None for x in entry.values())
            ):
                raise ValueError("CSV_ROW_SHAPE_INVALID")
            data.append(
                {
                    key: entry[column].strip() or None
                    for key, column in mapping.items()
                    if column in entry
                }
            )
        return {**envelope.metadata, "bars": data}
    except csv.Error:
        raise ValueError("CSV_INVALID") from None


def inspect_bundle(db, envelope, now):
    try:
        data = DatasetUpload.model_validate(read_bundle(envelope))
        validate_import(db, data, now)
    except ValidationError as exc:
        return None, {
            "valid": False,
            "error": "DATASET_SCHEMA_INVALID",
            "issues": [
                {
                    "field": ".".join(str(part) for part in item["loc"]),
                    "code": item["type"],
                }
                for item in exc.errors(
                    include_input=False, include_context=False, include_url=False
                )[:20]
            ],
        }
    except ValueError as exc:
        return None, {"valid": False, "error": str(exc)}
    expected = set(sessions(data.first_session, data.last_session))
    halted = set(data.suspended)
    active = {
        day
        for day in expected - halted
        if data.delisted_on is None or day < data.delisted_on
    }
    observed = {b.day for b in data.bars}
    missing = sorted(active - observed)
    report = {
        "valid": True,
        "ticker": data.ticker,
        "isin": data.isin,
        "source": data.source,
        "kind": data.kind,
        "first_session": data.first_session.isoformat(),
        "last_session": data.last_session.isoformat(),
        "source_timestamp": max(b.available_at for b in data.bars).isoformat(),
        "bars": len(data.bars),
        "expected": len(active),
        "halted": len(halted),
        "actions": len(data.actions),
        "actions_attested": data.actions_reviewed,
        "missing": [day.isoformat() for day in missing],
        "partial": bool(missing),
    }
    return data, report


def persist(db, envelope, now, channel, settings=None):
    settings = settings or ImportEnvironment()
    fingerprint = digest(envelope.model_dump(mode="json"))
    with writer(db):
        duplicate = db.scalar(
            select(MarketImport).where(MarketImport.fingerprint == fingerprint)
        )
        if duplicate:
            return {
                "id": duplicate.id,
                "dataset_id": duplicate.dataset_id,
                "status": duplicate.status,
                "duplicate": True,
                "report": duplicate.report,
            }
        day_start = now.astimezone(CAIRO).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        attempts = db.scalar(
            select(func.count())
            .select_from(MarketImport)
            .where(
                MarketImport.channel == channel,
                MarketImport.created >= day_start.timestamp(),
            )
        )
        if attempts >= settings.EOD_IMPORT_MAX_PER_DAY:
            return {
                "status": "QUOTA",
                "report": {"valid": False, "error": "IMPORT_DAILY_QUOTA"},
            }
        data, report = inspect_bundle(db, envelope, now)
        dataset_id = None
        status = "REJECTED"
        latest = None
        if data:
            row = import_dataset(db, data, now)
            dataset_id = row.id
            existing = db.scalar(
                select(MarketImport)
                .where(MarketImport.dataset_id == dataset_id)
                .limit(1)
            )
            status = (
                "DUPLICATE"
                if existing
                else "APPROVED_PARTIAL"
                if report["partial"]
                else "APPROVED"
            )
            if not existing and data.kind == "EQUITY":
                latest = max(b.day for b in data.bars).isoformat()
        record = MarketImport(
            fingerprint=fingerprint,
            dataset_id=dataset_id,
            ticker=report.get("ticker"),
            session=latest,
            created=now.timestamp(),
            channel=channel,
            status=status,
            report=report,
        )
        db.add(record)
        db.flush()
        return {
            "id": record.id,
            "dataset_id": dataset_id,
            "status": status,
            "duplicate": status == "DUPLICATE",
            "report": report,
        }


def generation(db, reference):
    return db.scalar(
        select(func.max(MarketImport.id)).where(MarketImport.session == reference)
    )


def scan_window(db, settings, reference, *, scheduled=True):
    key = f"{settings.revision}:{settings.mode}:{reference}"
    version = generation(db, reference) if scheduled else None
    return f"{key}:import:{version}" if version is not None else key


def approved_series(db, ticker, through, now, max_bars=250):
    security = db.get(EGXSecurity, ticker)
    if not security or not security.isin:
        return None, []
    # The approved dataset's original availability governs each candle. Keep an
    # entire series from the same version and stop at gaps or corporate actions.
    rows = db.scalars(
        select(SimulationDataset)
        .where(
            SimulationDataset.ticker == ticker,
            SimulationDataset.data["kind"].as_string() == "EQUITY",
            SimulationDataset.data["isin"].as_string() == security.isin,
            SimulationDataset.data["last_session"].as_string() >= through.isoformat(),
        )
        .order_by(SimulationDataset.imported.desc(), SimulationDataset.id.desc())
        .limit(12)
    )
    for row in rows:
        data = row.data
        latest_actions = {date.fromisoformat(x["day"]) for x in data["actions"]}
        received = {date.fromisoformat(v["day"]): v for v in data["bars"]}
        if through not in received:
            continue
        checked = []
        for day in reversed(
            sessions(date.fromisoformat(data["first_session"]), through)
        ):
            raw = received.get(day)
            if (
                not raw
                or day in latest_actions
                or datetime.fromisoformat(raw["available_at"]) > now
            ):
                break
            bar = DailyBar.model_validate(raw)
            if not bar.volume:
                break
            item = analyst_bar(ticker, bar, data["source"])
            item["available_at"] = raw["available_at"]
            checked.append(item)
            if len(checked) >= max_bars:
                break
        # Retain a current action-day close as a reference, never join the two price bases.
        if not checked and through in latest_actions:
            raw = received[through]
            if datetime.fromisoformat(raw["available_at"]) <= now:
                checked = [
                    analyst_bar(ticker, DailyBar.model_validate(raw), data["source"])
                ]
        if checked:
            return row.digest, CandleValidator.validate_bars(list(reversed(checked)))
    return None, []


def preferred_dataset(db, old_id, cursor):
    old = db.get(SimulationDataset, old_id)
    if not old:
        return old_id
    required = old.data
    newer = db.scalars(
        select(SimulationDataset)
        .where(
            SimulationDataset.ticker == old.ticker,
            SimulationDataset.data["kind"].as_string() == "EQUITY",
            SimulationDataset.data["last_session"].as_string()
            > required["last_session"],
            SimulationDataset.data["source"].as_string() == required["source"],
            SimulationDataset.data["reference"].as_string() == required["reference"],
            SimulationDataset.data["isin"].as_string() == required["isin"],
        )
        .order_by(SimulationDataset.imported.desc())
        .limit(8)
    )
    boundary = cursor.isoformat()
    for item in newer:
        candidate = item.data
        if any(
            required[k] != candidate[k]
            for k in ("listed_on", "first_session", "basis", "currency", "exchange")
        ):
            continue
        if candidate["delisted_on"] != required["delisted_on"]:
            continue
        if any(
            [
                v
                for v in required[key]
                if (v if key == "suspended" else v["day"]) <= boundary
            ]
            != [
                v
                for v in candidate[key]
                if (v if key == "suspended" else v["day"]) <= boundary
            ]
            for key in ("bars", "actions", "suspended")
        ):
            continue
        return item.id
    return old_id


def readiness(db, now):
    from app.models.candle import EGXCandle
    from app.services.data_provider.manager import default_provider_manager
    from app.services.scanner_calendar import COVERAGE, VERSION

    market = calendar_at(now)
    stocks = list(
        db.scalars(
            select(EGXSecurity)
            .where(EGXSecurity.listing_status == "ACTIVE")
            .order_by(EGXSecurity.ticker)
        )
    )
    raw = set(db.scalars(select(EGXCandle.ticker).distinct()))
    approved = list(
        db.scalars(
            select(SimulationDataset)
            .order_by(SimulationDataset.imported.desc())
            .limit(500)
        )
    )
    ids = {row.ticker for row in approved if row.data["kind"] == "EQUITY"}
    evidence = {}
    for row in approved:
        evidence.setdefault(row.ticker, row)
    current_day = market["completed_session"]
    result = []
    for security in stocks:
        ticker = security.ticker
        found = evidence.get(ticker)
        eligible = bool(
            found
            and found.data["kind"] == "EQUITY"
            and found.data["isin"] == security.isin
        )
        if current_day and (ticker in raw or ticker in ids):
            history = default_provider_manager.get_analytical_bars(
                ticker,
                db=db,
                allow_network=False,
                completed_session=date.fromisoformat(current_day),
            )
        else:
            history = {}
        latest = history.get("latest_session") or history.get(
            "latest_available_session"
        )
        if not latest and eligible:
            available = [
                item["day"]
                for item in found.data["bars"]
                if datetime.fromisoformat(item["available_at"]) <= now
            ]
            latest = max(available, default=None)
        reasons = []
        if not security.isin:
            reasons.append("INSTRUMENT_ID_MISSING")
        if not latest:
            reasons.append("DATA_UNAVAILABLE")
        elif latest != current_day:
            reasons.append("STALE_EOD")
        elif not history.get("current_analysis_eligible"):
            reasons.append("ANALYSIS_WARMUP_MISSING")
        if not eligible:
            reasons.extend(
                ["APPROVED_EXECUTION_DATA_MISSING", "CORPORATE_ACTION_EVIDENCE_MISSING"]
            )
        result.append(
            {
                "ticker": ticker,
                "name": security.arabic_name,
                "latest": latest,
                "source": history.get("actual_provider")
                or (found.data["source"] if eligible and latest else None),
                "raw": ticker in raw,
                "current": bool(latest and latest == current_day),
                "analysis": bool(history.get("current_analysis_eligible")),
                "paper_dataset": eligible,
                "backtest_dataset": eligible and len(found.data["bars"]) >= 200
                if eligible
                else False,
                "reasons": reasons,
            }
        )
    last = db.scalar(
        select(MarketImport)
        .where(MarketImport.status.in_(["APPROVED", "APPROVED_PARTIAL"]))
        .order_by(MarketImport.id.desc())
        .limit(1)
    )
    counts = {
        "listed": len(stocks),
        "with_history": sum(
            bool(r["latest"] or r["raw"] or r["paper_dataset"]) for r in result
        ),
        "current": sum(r["current"] for r in result),
        "analysis": sum(r["analysis"] for r in result),
        "stale": sum("STALE_EOD" in r["reasons"] for r in result),
        "unavailable": sum("DATA_UNAVAILABLE" in r["reasons"] for r in result),
        "paper": sum(r["paper_dataset"] for r in result),
        "backtest_candidates": sum(r["backtest_dataset"] for r in result),
        "missing_identity": sum(not s.isin for s in stocks),
        "missing_corporate_actions": sum(
            "CORPORATE_ACTION_EVIDENCE_MISSING" in r["reasons"] for r in result
        ),
    }
    return {
        "counts": counts,
        "items": result,
        "completed_session": current_day,
        "calendar": {"version": VERSION, "coverage": [x.isoformat() for x in COVERAGE]},
        "last_import": last.created if last else None,
        "source_timestamp": last.report["source_timestamp"] if last else None,
        "benchmarks": [
            {
                "ticker": row.ticker,
                "kind": row.data["kind"],
                "bars": len(row.data["bars"]),
                "from": row.data["first_session"],
                "through": row.data["last_session"],
            }
            for row in approved
            if row.data["kind"] != "EQUITY"
        ],
        "verified_realtime": False,
        "polling_active": False,
    }
