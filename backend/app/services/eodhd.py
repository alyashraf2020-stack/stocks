"""Personal EODHD sync, with a SQLite write fence before every billable request."""

from base64 import urlsafe_b64encode
from datetime import UTC, date, datetime, timedelta
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock, Timeout
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from app.integrations.thndr_auth import IntegrationError, Vault
from app.models.eodhd import EodhdCandle, EodhdConfig, EodhdSync, EodhdUsage
from app.models.security import EGXSecurity
from app.services.data_provider.eodhd import (
    CODE,
    PROVIDER,
    TOKEN,
    EodhdProvider,
    ProviderError,
)
from app.services.scanner_calendar import CAIRO, calendar_at, hours
from app.services.scanner_repository import load_settings, writer
from app.services.sharia_filter import status_for
from app.services.validator import completed_analytical_bars
from app.workers.trading_scheduler import eod_due

DAILY_LIMIT = 20
RETRY_SECONDS = 30 * 60
# Verified EGX registry identity and the owner's successful Free-plan probe.
BOOTSTRAP = {"SWDY": "EGS3G0Z1C014"}
TRANSIENT = {"UPSTREAM_UNAVAILABLE", "RATE_LIMITED", "EOD_PENDING", "INVALID_RESPONSE"}


def utcnow():
    return datetime.now(UTC)


def cipher():
    key = os.getenv("EODHD_ENCRYPTION_KEY")
    if not key:
        # Existing personal installations already provision a separate local key.
        parent = os.getenv("NOTIFICATION_ENCRYPTION_KEY", "")
        try:
            Fernet(parent)
        except (ValueError, TypeError):
            raise ProviderError("ENCRYPTION_KEY_REQUIRED") from None
        key = urlsafe_b64encode(
            hmac.digest(parent.encode(), b"egx-eodhd-token-v1", "sha256")
        )
    try:
        return Fernet(key)
    except (ValueError, TypeError):
        raise ProviderError("ENCRYPTION_KEY_REQUIRED") from None


def lock_for(db):
    path = db.get_bind().url.database
    if db.get_bind().dialect.name != "sqlite" or not path or path == ":memory:":
        raise ProviderError("PRIVATE_SQLITE_REQUIRED")
    return FileLock(path + ".eodhd.lock", timeout=0, mode=0o600)


def configure(db, settings, token):
    if token is not None and (
        not isinstance(token, str) or not TOKEN.fullmatch(token) or token == "demo"
    ):
        raise ProviderError("INVALID_TOKEN_FORMAT")
    with lock_for(db), writer(db):
        row = db.get(EodhdConfig, 1)
        if not row:
            row = EodhdConfig(id=1, catalog={})
            db.add(row)
        if token is not None:
            row.encrypted_token = cipher().encrypt(token.encode()).decode()
            row.last_status = None
            row.checked = None
        for key, value in settings.items():
            setattr(row, key, value)
        if row.enabled and (not row.encrypted_token or not row.exclusive):
            raise ProviderError("EXCLUSIVE_FREE_ACCOUNT_REQUIRED")
        if row.automatic and not row.enabled:
            raise ProviderError("ENABLE_PROVIDER_FIRST")


def remove_token(db):
    with lock_for(db), writer(db):
        row = db.get(EodhdConfig, 1)
        if row:
            row.encrypted_token = row.last_status = row.checked = None
            row.enabled = row.automatic = row.exclusive = False


def status(db, clock):
    row = db.get(EodhdConfig, 1)
    usage = db.get(EodhdUsage, clock.date().isoformat())
    latest = db.scalars(select(EodhdSync).order_by(EodhdSync.tried.desc()).limit(25))
    market = calendar_at(clock)
    current = market["completed_session"]
    reset = datetime.combine(clock.date() + timedelta(days=1), datetime.min.time(), UTC)
    return {
        "enabled": bool(row and row.enabled),
        "automatic": bool(row and row.automatic),
        "retry": bool(row and row.retry),
        "exclusive": bool(row and row.exclusive),
        "configured": bool(row and row.encrypted_token),
        "connection": row.last_status if row else None,
        "checked_at": row.checked if row else None,
        "utc_day": clock.date().isoformat(),
        "resets_at": reset.isoformat(),
        "limit": DAILY_LIMIT,
        "reserved": usage.reserved if usage else 0,
        "account_used": usage.upstream if usage else None,
        "projected": usage.projected if usage else 0,
        "remaining": max(0, DAILY_LIMIT - usage.projected) if usage else DAILY_LIMIT,
        "mapped": len(set(BOOTSTRAP) | set(row.catalog if row else {})),
        "completed_session": current,
        "symbols": [
            {
                "ticker": item.ticker,
                "status": item.status,
                "last_attempt": item.tried,
                "next_retry": item.next_try,
                "last_session": (
                    last := db.scalar(
                        select(func.max(EodhdCandle.session_date)).where(
                            EodhdCandle.ticker == item.ticker
                        )
                    )
                ),
                "freshness": "VALIDATED_EOD"
                if last and last == current
                else "STALE"
                if last and current
                else "UNAVAILABLE",
            }
            for item in latest
        ],
    }


def reserve(db, clock, upstream, *, charge):
    day = clock.date().isoformat()
    with writer(db):
        usage = db.get(EodhdUsage, day)
        if not usage:
            usage = EodhdUsage(day=day, reserved=0, projected=0)
            db.add(usage)
        usage.upstream = upstream
        usage.projected = max(usage.projected, upstream)
        if not charge:
            return True
        if usage.reserved >= DAILY_LIMIT or usage.projected >= DAILY_LIMIT:
            return False
        usage.reserved += 1
        usage.projected += 1
        return True


def mapped_ticker(db, config, ticker):
    security = db.get(EGXSecurity, ticker)
    if (
        not security
        or security.listing_status != "ACTIVE"
        or not security.isin
        or not CODE.fullmatch(ticker)
    ):
        raise ProviderError("UNKNOWN_EGX_EQUITY")
    catalog = {**BOOTSTRAP, **config.catalog}
    if ticker not in catalog or (catalog[ticker] and catalog[ticker] != security.isin):
        raise ProviderError("SYMBOL_MAPPING_UNVERIFIED")
    return security.isin


def verified_rows(raw, start, end, ticker):
    bars = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(item["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if day < start or day > end or not isinstance(hours(day), tuple):
            continue
        values = {
            name: item.get(name) for name in ("open", "high", "low", "close", "volume")
        }
        if any(type(value) not in (int, float) for value in values.values()):
            continue
        # Historical prices are raw OHLC. Adjusted close never replaces raw close.
        bars.append(
            {
                "ticker": ticker,
                "session_date": day.isoformat(),
                "exchange": "EGX",
                "currency": "EGP",
                "actual_provider": PROVIDER,
                **values,
            }
        )
    return [
        bar
        for bar in completed_analytical_bars(bars, end, ticker)
        if bar["validation_status"] == "VALID"
    ]


def mark(db, code, clock):
    with writer(db):
        row = db.get(EodhdConfig, 1)
        if row:
            row.last_status, row.checked = code, clock.timestamp()


def network(db, action, *, ticker=None, auto=False, provider=None, clock=utcnow):
    provider = provider or EodhdProvider()
    try:
        with lock_for(db):
            return _network(db, action, ticker, auto, provider, clock)
    except Timeout:
        raise ProviderError("SYNC_BUSY") from None


def _network(db, action, ticker, auto, provider, clock):
    stamp = clock()
    market = calendar_at(stamp)
    periodic = action == "history"
    end = start = None
    config = db.get(EodhdConfig, 1)
    if not config or not config.encrypted_token:
        raise ProviderError("TOKEN_REQUIRED")
    if action != "test" and (
        not config.enabled or not config.exclusive or (auto and not config.automatic)
    ):
        raise ProviderError("PROVIDER_DISABLED")
    try:
        token = cipher().decrypt(config.encrypted_token.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise ProviderError("ENCRYPTION_KEY_MISMATCH") from None
    if periodic:
        target = market["completed_session"]
        if not target or stamp.timestamp() < eod_due(market):
            raise ProviderError("EOD_WINDOW_PENDING")
        end = date.fromisoformat(target)
        isin = mapped_ticker(db, config, ticker)
        last = db.scalar(
            select(func.max(EodhdCandle.session_date)).where(
                EodhdCandle.ticker == ticker, EodhdCandle.isin == isin
            )
        )
        if last and last >= target:
            return {"status": "VALIDATED_EOD", "added": 0}
        # Re-read a short overlap to recover earlier publication gaps without
        # replacing already validated observations or re-fetching a full year.
        start = (
            max(end - timedelta(days=364), date.fromisoformat(last) - timedelta(days=6))
            if last
            else end - timedelta(days=364)
        )
        sync = db.get(EodhdSync, ticker)
        attempts = (
            sync.attempts
            if sync
            and sync.target == target
            and datetime.fromtimestamp(sync.tried, UTC).date() == stamp.date()
            else 0
        )
        if sync and stamp.timestamp() < sync.next_try:
            raise ProviderError("RETRY_COOLDOWN")
        if auto and attempts and (not config.retry or attempts >= 2):
            raise ProviderError("RETRY_PAUSED")
    db.rollback()

    if action != "test" and stamp.hour == 23 and stamp.minute == 59:
        raise ProviderError("UTC_RESET_WINDOW")
    try:
        remote = provider.usage(token, stamp.date())
    except ProviderError as error:
        mark(db, str(error), clock())
        raise
    if clock().date() != stamp.date():
        raise ProviderError("UTC_RESET_WINDOW")
    if not reserve(db, stamp, remote, charge=action != "test"):
        mark(db, "FREE_QUOTA_EXHAUSTED", clock())
        raise ProviderError("FREE_QUOTA_EXHAUSTED")
    if action == "test":
        mark(db, "CONNECTED", clock())
        return {"status": "CONNECTED"}
    if periodic:
        with writer(db):
            db.merge(
                EodhdSync(
                    ticker=ticker,
                    target=target,
                    attempts=attempts + 1,
                    tried=stamp.timestamp(),
                    next_try=stamp.timestamp() + RETRY_SECONDS,
                    status="PENDING",
                )
            )
    try:
        fetched = clock()
        if fetched.date() != stamp.date() or (
            fetched.hour == 23 and fetched.minute == 59
        ):
            raise ProviderError("UTC_RESET_WINDOW")
        if action == "catalog":
            catalog = provider.catalog(token)
            with writer(db):
                db.get(EodhdConfig, 1).catalog = catalog
            result = {"status": "CATALOG_READY", "mapped": len(catalog)}
        else:
            raw = provider.history(token, ticker, start, end)
            bars = verified_rows(raw, start, end, ticker)
            with writer(db):
                added = 0
                for bar in bars:
                    stmt = insert(EodhdCandle).values(
                        ticker=ticker,
                        session_date=bar["session_date"],
                        isin=isin,
                        fetched=clock().timestamp(),
                        bar=bar,
                    )
                    added += db.execute(stmt.on_conflict_do_nothing()).rowcount
            result = {
                "status": "VALIDATED_EOD"
                if any(b["session_date"] == target for b in bars)
                else "EOD_PENDING",
                "added": added,
            }
    except ProviderError as error:
        result = {"status": str(error)}
    finished = clock()
    code = result["status"]
    with writer(db):
        row = db.get(EodhdConfig, 1)
        row.last_status, row.checked = code, finished.timestamp()
        if periodic:
            sync = db.get(EodhdSync, ticker)
            sync.status = code
            wait = (
                RETRY_SECONDS
                if code in TRANSIENT
                else 86400
                if code == "SYMBOL_UNAVAILABLE"
                else 0
            )
            sync.next_try = finished.timestamp() + wait
    return result


def priority(db, now, broker_positions):
    row = db.get(EodhdConfig, 1)
    if not row or not row.enabled or not row.automatic:
        return []
    settings = load_settings(db)
    manual = (
        {p.ticker for p in (settings.manual.positions or [])}
        if settings.manual
        else set()
    )
    holdings = {**{ticker: None for ticker in manual}, **broker_positions}
    watchlist = {ticker: index for index, ticker in enumerate(settings.watchlist)}
    current = calendar_at(now)["completed_session"]
    if not current:
        return []
    catalog = {**BOOTSTRAP, **row.catalog}
    securities = db.scalars(
        select(EGXSecurity).where(
            EGXSecurity.listing_status == "ACTIVE", EGXSecurity.ticker.in_(catalog)
        )
    ).all()
    latest = dict(
        db.execute(
            select(EodhdCandle.ticker, func.max(EodhdCandle.session_date))
            .join(
                EGXSecurity,
                (EGXSecurity.ticker == EodhdCandle.ticker)
                & (EGXSecurity.isin == EodhdCandle.isin),
            )
            .group_by(EodhdCandle.ticker)
        ).all()
    )
    observed = {item.ticker: item for item in db.scalars(select(EodhdSync))}
    picks = []
    for security in securities:
        ticker = security.ticker
        if (
            not security.isin
            or latest.get(ticker, "") >= current
            or catalog[ticker] not in (None, security.isin)
        ):
            continue
        item = observed.get(ticker)
        if item:
            same_day = datetime.fromtimestamp(item.tried, UTC).date() == now.date()
            if item.next_try > now.timestamp() or (
                item.target == current
                and same_day
                and (not row.retry or item.attempts >= 2)
            ):
                continue
        tier = (
            0
            if ticker in holdings and holdings[ticker] in (None, security.isin)
            else 1
            if ticker in watchlist
            else 2
            if status_for(db, security, now.astimezone(CAIRO).date())["status"]
            == "COMPLIANT"
            else 3
        )
        picks.append(
            (
                tier,
                latest.get(ticker, ""),
                item.tried if item else 0,
                watchlist.get(ticker, 0),
                ticker,
            )
        )
    return [ticker for *_, ticker in sorted(picks)]


async def brokerage_positions(now):
    # Read only the already-authorized local snapshot. No MCP request or write.
    try:
        async with Vault().locked() as data:
            if (
                data.get("revoking")
                or data.get("reauth")
                or (data.get("tokens") or {}).get("expires_at", 0) <= now.timestamp()
            ):
                return {}
            return {
                row["ticker"]: row["instrument_id"]
                for row in ((data.get("portfolio") or {}).get("holdings") or [])
                if row.get("instrument_id") and row.get("ticker")
            }
    except IntegrationError:
        return {}


def automatic(factory, now):
    import asyncio

    with factory() as db:
        config = db.get(EodhdConfig, 1)
        usage = db.get(EodhdUsage, now.date().isoformat())
        due = eod_due(calendar_at(now))
        if (
            not config
            or not config.enabled
            or not config.automatic
            or not due
            or now.timestamp() < due
            or (usage and usage.projected >= DAILY_LIMIT)
        ):
            return
        if config.checked and config.last_status in {
            "UPSTREAM_UNAVAILABLE",
            "RATE_LIMITED",
            "AUTH_FAILED",
            "ACCESS_DENIED",
            "USAGE_UNVERIFIED",
            "FREE_PLAN_UNVERIFIED",
            "FREE_QUOTA_EXHAUSTED",
        }:
            pause = (
                86400
                if config.last_status
                in {"AUTH_FAILED", "ACCESS_DENIED", "FREE_PLAN_UNVERIFIED"}
                else RETRY_SECONDS
            )
            if now.timestamp() < config.checked + pause:
                return
        broker = asyncio.run(brokerage_positions(now))
        picks = priority(db, now, broker)
        if not picks:
            return
        db.rollback()
        try:
            network(db, "history", ticker=picks[0], auto=True)
        except ProviderError:
            pass  # The status contains only sanitized codes. No retry in this cycle.
