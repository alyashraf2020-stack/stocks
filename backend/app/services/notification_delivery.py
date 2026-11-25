"""Transactional fan-out and independent leases for each external destination."""

import hmac
import json
import re
import secrets
import time
from datetime import datetime
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select

from app.integrations.telegram_client import TOKEN, Telegram, TransportError
from app.integrations.web_push import configured_pair
from app.integrations.web_push import deliver as web_push
from app.models.delivery import (
    ChannelDelivery,
    ChannelThrottle,
    DeliverySetting,
    DeliveryTarget,
)
from app.models.notification import Notification
from app.models.security import EGXSecurity
from app.models.trading_signal import TradingSignal
from app.schemas.notification_settings import DeliveryEnvironment, DeliveryPreferences
from app.services.risk_policy import entry_blocks, load_policy
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_repository import digest, writer
from app.services.sharia_filter import status_for

SEVERITIES = ("INFO", "OPPORTUNITY", "WARNING", "CRITICAL")
CHANNELS = {"TELEGRAM": "telegram", "PUSH": "push"}
LEASE = 35
MAX_ATTEMPTS = 5
ACTIVE = ("PENDING", "SENDING")
TEXT = {
    "BUY_REVIEW": "فرصة شراء للمراجعة",
    "SELL_REVIEW": "مركز يحتاج مراجعة",
    "ENTRY_ZONE": "تغيّر نطاق الدخول",
    "BREAKOUT": "إشارة اختراق للمراجعة",
    "RATING_CHANGE": "التقييم الفني اتغيّر",
    "STOP": "رصد مستوى الوقف",
    "TARGET": "رصد مستوى الهدف",
    "PORTFOLIO_RISK": "مراجعة مخاطر المحفظة",
    "SHARIA_CHANGE": "الفحص الشرعي اتغيّر",
    "MARKET_DATA": "مشكلة في بيانات السوق",
    "THNDR_CONNECTION": "اتصال ثاندر يحتاج مراجعة",
    "SCANNER_FAILURE": "مشكلة في الماسح",
    "KILL_SWITCH": "الإيقاف الطارئ اتفعّل",
    "TECHNICAL_CHANGE": "تغيّر فني",
    "PAPER_FILL": "تنفيذ افتراضي اتسجّل",
    "PAPER_REJECTED": "أمر افتراضي مرفوض",
    "BACKTEST_COMPLETED": "الاختبار التاريخي خلص",
    "BACKTEST_FAILED": "الاختبار التاريخي تعذّر",
    "DELIVERY_TEST": "اختبار إشعارات EGX",
}
REASONS = {
    "BUY_REVIEW": "الشروط الفنية اتجمّعت في الجلسة المرجعية",
    "STOP_LEVEL_OBSERVED": "مستوى الوقف اتلمس في البيانات المرجعية",
    "TARGET_1_OBSERVED": "أول هدف اتلمس في البيانات المرجعية",
    "WAIT_FOR_BREAKOUT": "السعر محتاج تأكيد الاختراق",
    "DATA_UNAVAILABLE": "بيانات الجلسة غير كافية",
    "KILL_SWITCH": "سياسة المخاطر أوقفت الدخول الجديد",
}
FRESH = {
    "HISTORICAL": "تاريخية",
    "DELAYED": "متأخرة",
    "REALTIME_VERIFIED": "لحظية متحقّق منها",
    "STALE": "قديمة",
    "UNKNOWN": "غير متاحة",
}
ENTRY = {"BUY_REVIEW", "ENTRY_ZONE", "BREAKOUT"}


def env():
    return DeliveryEnvironment()


def configuration(environment):
    try:
        Fernet(environment.NOTIFICATION_ENCRYPTION_KEY)
    except (ValueError, TypeError):
        return {"TELEGRAM": False, "PUSH": False}
    host = environment.APP_HOST
    ready = bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,250})\.[a-z]{2,63}", host))
    return {
        "TELEGRAM": bool(
            ready
            and environment.TELEGRAM_ENABLED
            and TOKEN.fullmatch(environment.TELEGRAM_BOT_TOKEN)
        ),
        "PUSH": bool(
            ready
            and environment.WEB_PUSH_ENABLED
            and configured_pair(
                environment.VAPID_PRIVATE_KEY,
                environment.VAPID_PUBLIC_KEY,
                environment.VAPID_SUBJECT,
            )
        ),
    }


def encrypt(environment, data):
    return (
        Fernet(environment.NOTIFICATION_ENCRYPTION_KEY)
        .encrypt(json.dumps(data).encode())
        .decode()
    )


def decrypt(environment, blob):
    try:
        return json.loads(Fernet(environment.NOTIFICATION_ENCRYPTION_KEY).decrypt(blob))
    except (ValueError, InvalidToken):
        raise TransportError("DESTINATION_STORAGE_UNREADABLE", permanent=True) from None


def prefs(db):
    row = db.get(DeliverySetting, 1)
    return (
        DeliveryPreferences.model_validate(row.data) if row else DeliveryPreferences()
    )


def setting(db):
    row = db.get(DeliverySetting, 1)
    if row is None:
        row = DeliverySetting(id=1, data=DeliveryPreferences().model_dump())
        db.add(row)
        db.flush()
    return row


def set_prefs(db, data, now):
    if (
        (data.quiet_start is None) != (data.quiet_end is None)
        or data.quiet_start == data.quiet_end
        and data.quiet_start is not None
    ):
        raise ValueError("QUIET_HOURS_INVALID")
    if set(data.muted) - TEXT.keys() or "DELIVERY_TEST" in data.muted:
        raise ValueError("NOTIFICATION_CATEGORY_INVALID")
    with writer(db):
        row = setting(db)
        before = DeliveryPreferences.model_validate(row.data)
        if before.revision != data.revision:
            raise ValueError("SETTINGS_CHANGED")
        row.data = data.model_copy(
            update={"revision": before.revision + 1}
        ).model_dump()
        for target in db.scalars(
            select(DeliveryTarget).where(DeliveryTarget.active.is_(True))
        ):
            field = CHANNELS[target.channel]
            if getattr(before, field) != getattr(data, field):
                target.version += 1
                target.since = now
        return row.data


def pair_start(db, now, environment):
    if not configuration(environment)["TELEGRAM"]:
        raise ValueError("TELEGRAM_NOT_CONFIGURED")
    bot = Telegram(environment.TELEGRAM_BOT_TOKEN).bot()
    nonce = secrets.token_urlsafe(24)
    with writer(db):
        row = setting(db)
        row.pair_hash = digest(nonce)
        row.pair_expires = now + 600
        row.next_pair_check = now
    return {"url": "https://t.me/" + bot + "?start=" + nonce, "expires": now + 600}


def paired_chat(updates, nonce_hash, expires_at, now, owner_id=None):
    authorized = set()
    for item in updates:
        message = item.get("message", {}) if isinstance(item, dict) else {}
        if not isinstance(message, dict):
            continue
        chat, sender = message.get("chat"), message.get("from")
        if (
            not isinstance(chat, dict)
            or not isinstance(sender, dict)
            or not isinstance(message.get("text"), str)
        ):
            continue
        match = re.fullmatch(r"/start ([a-zA-Z0-9_-]{32})", message.get("text", ""))
        created, chat_id = message.get("date"), chat.get("id")
        if (
            match
            and isinstance(created, int)
            and expires_at - 601 <= created <= min(expires_at, now)
            and chat.get("type") == "private"
            and isinstance(chat_id, int)
            and chat_id > 0
            and sender.get("id") == chat_id
            and not sender.get("is_bot")
            and (owner_id is None or chat_id == owner_id)
            and hmac.compare_digest(digest(match[1]), nonce_hash)
        ):
            authorized.add(chat_id)
    return next(iter(authorized)) if len(authorized) == 1 else None


def pair_check(factory, now, environment):
    if not configuration(environment)["TELEGRAM"]:
        raise ValueError("TELEGRAM_NOT_CONFIGURED")
    with factory() as db, writer(db):
        row = setting(db)
        if not row.pair_hash or row.pair_expires <= now:
            raise ValueError("PAIR_EXPIRED")
        if row.next_pair_check and row.next_pair_check > now:
            raise ValueError("PAIR_RATE_LIMITED")
        wanted, expires_at = row.pair_hash, row.pair_expires
        row.next_pair_check = now + 3
    try:
        updates = Telegram(environment.TELEGRAM_BOT_TOKEN).updates()
    except TransportError as error:
        if error.retry:
            with factory() as db, writer(db):
                row = setting(db)
                if row.pair_hash == wanted:
                    row.next_pair_check = now + max(3, error.retry)
        raise
    chat_id = paired_chat(
        updates, wanted, expires_at, now, environment.TELEGRAM_OWNER_USER_ID
    )
    if chat_id is None:
        return {"paired": False}
    with factory() as db, writer(db):
        row = setting(db)
        if row.pair_hash != wanted or row.pair_expires <= time.time():
            return {"paired": False}
        row.pair_hash, row.pair_expires = None, None
        install_target(
            db,
            "TELEGRAM",
            "محادثة تيليجرام الخاصة",
            "owner",
            {
                "chat_id": chat_id,
                "bot_key": digest(environment.TELEGRAM_BOT_TOKEN),
            },
            now,
            environment,
        )
    return {"paired": True}


def install_target(db, channel, label, identity, destination, now, environment):
    key = digest([channel, identity])
    current = db.get(DeliveryTarget, key)
    secret = encrypt(environment, destination)
    if current:
        current.label, current.secret = label, secret
        current.active, current.since, current.last_ok = True, now, None
        current.version += 1
    else:
        if (
            channel == "PUSH"
            and len(
                list(
                    db.scalars(
                        select(DeliveryTarget.id)
                        .where(
                            DeliveryTarget.channel == channel,
                            DeliveryTarget.active.is_(True),
                        )
                        .limit(12)
                    )
                )
            )
            >= 12
        ):
            raise ValueError("DEVICE_LIMIT")
        db.add(
            DeliveryTarget(
                id=key,
                channel=channel,
                label=label,
                active=True,
                since=now,
                version=1,
                secret=secret,
            )
        )
    return key


def revoke(db, identity):
    with writer(db):
        target = db.get(DeliveryTarget, identity)
        if not target:
            return False
        target.active, target.secret = False, ""
        target.version += 1
        if target.channel == "TELEGRAM":
            row = setting(db)
            row.pair_hash, row.pair_expires = None, None
    return True


def add_delivery(db, target, note_id, series, now, *, test=False):
    key = digest([target.id, target.version, note_id])
    if not db.get(ChannelDelivery, key):
        db.add(
            ChannelDelivery(
                id=key,
                version=target.version,
                target_id=target.id,
                channel=target.channel,
                notification_id=note_id,
                series=series,
                created=now,
                due=now,
                status="PENDING",
                attempts=0,
                history=[],
                test=test,
            )
        )


def wanted(settings, note):
    return note.category not in settings.muted and SEVERITIES.index(
        note.severity
    ) >= SEVERITIES.index(settings.severity)


def fanout(db, note_id):
    note = db.get(Notification, note_id)
    settings = prefs(db)
    if not wanted(settings, note):
        return
    configured = configuration(env())
    enabled = [
        channel
        for channel, field in CHANNELS.items()
        if configured[channel] and getattr(settings, field)
    ]
    if enabled:
        for target in db.scalars(
            select(DeliveryTarget).where(
                DeliveryTarget.active.is_(True),
                DeliveryTarget.channel.in_(enabled),
                DeliveryTarget.since <= note.created,
            )
        ):
            add_delivery(db, target, note.id, note.series, note.created)


def test_message(db, channel, identity, now, environment):
    if channel not in CHANNELS or not configuration(environment)[channel]:
        raise ValueError("CHANNEL_NOT_CONFIGURED")
    with writer(db):
        target = db.get(DeliveryTarget, identity)
        if (
            not target
            or not target.active
            or target.channel != channel
            or not getattr(prefs(db), CHANNELS[channel])
        ):
            raise ValueError("DESTINATION_NOT_AUTHORIZED")
        previous = db.scalar(
            select(ChannelDelivery.id)
            .where(
                ChannelDelivery.target_id == identity,
                ChannelDelivery.test.is_(True),
                ChannelDelivery.created > now - 60,
            )
            .limit(1)
        )
        if previous:
            raise ValueError("DELIVERY_TEST_RATE_LIMIT")
        add_delivery(db, target, uuid4().hex, "TEST", now, test=True)


def quiet(settings, now, severity):
    if settings.quiet_start is None or (
        severity == "CRITICAL" and settings.critical_bypass
    ):
        return False
    clock = datetime.fromtimestamp(now, CAIRO)
    minute = clock.hour * 60 + clock.minute
    start, end = settings.quiet_start, settings.quiet_end
    return start <= minute < end if start < end else minute >= start or minute < end


def opportunity_current(db, note, now):
    if note.severity != "OPPORTUNITY" and note.category not in ENTRY:
        return True
    payload = note.payload
    expiry = payload.get("_signal_expires")
    instrument = (
        db.get(EGXSecurity, payload.get("ticker")) if payload.get("ticker") else None
    )
    try:
        current = calendar_at(datetime.fromtimestamp(now, CAIRO))
        if (
            not expiry
            or datetime.fromisoformat(expiry).timestamp() <= now
            or not instrument
            or instrument.isin != payload.get("_instrument")
            or instrument.listing_status != "ACTIVE"
            or not current["completed_session"]
            or current["completed_session"] != payload.get("_ref_session")
            or current["session_status"] == "HALTED"
            or payload.get("freshness") != "HISTORICAL"
        ):
            return False
    except (ValueError, TypeError):
        return False
    if payload.get("_fingerprint"):
        latest = db.get(TradingSignal, (payload.get("_scope"), instrument.ticker))
        if not latest or latest.fingerprint != payload["_fingerprint"]:
            return False
    policy = load_policy(db)
    sharia = (
        status_for(db, instrument, datetime.fromtimestamp(now, CAIRO).date())["status"]
        if policy.islamic_mode
        else None
    )
    return not entry_blocks(policy, sharia, advanced_supported=False)


def redact(note, detailed, host):
    title = "EGX · " + TEXT.get(note.category, "إشعار جديد")
    message = "افتح التطبيق الخاص بيك للمراجعة."
    if detailed and not note.series.startswith("THNDR_PORTFOLIO:"):
        data = note.payload
        ticker = data.get("ticker", "")
        ticker = (
            ticker
            if isinstance(ticker, str) and re.fullmatch(r"[A-Z0-9._-]{1,20}", ticker)
            else ""
        )
        basis = FRESH.get(data.get("freshness"), "غير متاحة")
        reason = REASONS.get(
            data.get("reason"), TEXT.get(note.category, "راجع التفاصيل")
        )
        timestamp = data.get("source_timestamp")
        try:
            parsed = (
                datetime.fromisoformat(timestamp)
                if isinstance(timestamp, str)
                else None
            )
            when = (
                parsed.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M") + " القاهرة"
                if parsed and parsed.tzinfo
                else "غير متاح"
            )
        except ValueError:
            when = "غير متاح"
        title += " · " + ticker if ticker else ""
        message = (
            f"{reason}\nالبيانات {basis} · وقت الرصد {when}\nللمراجعة داخل التطبيق."
        )
    return {
        "title": title,
        "body": message,
        "path": "/notifications",
        "url": f"https://{host}/notifications",
        "tag": note.id,
    }


def claim(db, channel, now, environment):
    with writer(db):
        if not configuration(environment)[channel]:
            return None
        throttle = db.get(ChannelThrottle, channel)
        if throttle and throttle.until > now:
            return None
        if db.scalar(
            select(ChannelDelivery.id)
            .where(
                ChannelDelivery.channel == channel,
                ChannelDelivery.status == "SENDING",
                ChannelDelivery.lease > now,
            )
            .limit(1)
        ):
            return None
        settings = prefs(db)
        rows = db.scalars(
            select(ChannelDelivery)
            .where(
                ChannelDelivery.channel == channel,
                ChannelDelivery.status.in_(ACTIVE),
                ChannelDelivery.due <= now,
            )
            .order_by(ChannelDelivery.due, ChannelDelivery.id)
            .limit(32)
        ).all()
        for row in rows:
            if row.status == "SENDING":
                row.history = [*row.history, {"at": now, "result": "LEASE_RECOVERED"}]
            target = db.get(DeliveryTarget, row.target_id)
            note = None if row.test else db.get(Notification, row.notification_id)
            expiry = row.created + 300 if row.test else note.expires if note else 0
            invalid = (
                not target
                or not target.active
                or target.version != row.version
                or not getattr(settings, CHANNELS[channel])
                or not row.test
                and (
                    not note
                    or not wanted(settings, note)
                    or not opportunity_current(db, note, now)
                )
            )
            if expiry <= now or invalid or row.attempts >= MAX_ATTEMPTS:
                row.status = (
                    "EXPIRED"
                    if expiry <= now
                    else "SUPPRESSED"
                    if invalid
                    else "FAILED"
                )
                row.error = (
                    "RETRY_LIMIT" if row.status == "FAILED" else "NO_LONGER_ELIGIBLE"
                )
                row.token, row.lease = None, None
                continue
            severity = note.severity if note else "INFO"
            if not row.test and quiet(settings, now, severity):
                row.status, row.due, row.token, row.lease = (
                    "PENDING",
                    now + 60,
                    None,
                    None,
                )
                continue
            if settings.cooldown and note and severity != "CRITICAL":
                delivered = db.scalar(
                    select(ChannelDelivery.id)
                    .where(
                        ChannelDelivery.series == row.series,
                        ChannelDelivery.target_id == target.id,
                        ChannelDelivery.status == "DELIVERED",
                        ChannelDelivery.due > now - settings.cooldown,
                    )
                    .limit(1)
                )
                if delivered:
                    row.status, row.error = "SUPPRESSED", "COOLDOWN"
                    continue
            row.status, row.token, row.lease = "SENDING", uuid4().hex, now + LEASE
            row.attempts += 1
            row.due = row.lease
            db.merge(ChannelThrottle(channel=channel, until=now + 1))
            payload = (
                redact(note, settings.detailed, environment.APP_HOST)
                if note
                else {
                    "title": TEXT["DELIVERY_TEST"],
                    "body": "الإشعار ده اختبار بطلب المالك.",
                    "path": "/notifications",
                    "tag": row.id,
                    "url": f"https://{environment.APP_HOST}/notifications",
                }
            )
            return row.id, row.token, target.secret, payload, int(expiry - now)


def finish(db, key, token, now, error=None):
    with writer(db):
        row = db.get(ChannelDelivery, key)
        if not row or row.status != "SENDING" or row.token != token or row.lease <= now:
            return False
        target = db.get(DeliveryTarget, row.target_id)
        row.token, row.lease = None, None
        row.error = error.code if error else None
        row.history = [
            *row.history,
            {"at": now, "result": error.code if error else "DELIVERED"},
        ]
        if error:
            row.status = (
                "FAILED"
                if error.permanent or row.attempts >= MAX_ATTEMPTS
                else "PENDING"
            )
            row.due = now + max(error.retry or 0, 15 * 2 ** (row.attempts - 1))
            if error.retry and error.code.endswith("RATE_LIMITED"):
                db.merge(ChannelThrottle(channel=row.channel, until=now + error.retry))
            if error.revoke and target and target.version == row.version:
                target.active, target.secret = False, ""
                target.version += 1
        else:
            row.status, row.due = "DELIVERED", now
            if target and target.version == row.version:
                target.last_ok = now
        return True


def delivery_step(factory, channel, clock, environment):
    with factory() as db:
        claimed = claim(db, channel, clock(), environment)
    if not claimed:
        return False
    key, token, secret, payload, ttl = claimed
    error = None
    try:
        destination = decrypt(environment, secret)
        if channel == "TELEGRAM":
            if not hmac.compare_digest(
                destination.get("bot_key", ""), digest(environment.TELEGRAM_BOT_TOKEN)
            ):
                raise TransportError("TELEGRAM_REPAIR_REQUIRED", permanent=True)
            Telegram(environment.TELEGRAM_BOT_TOKEN).deliver(
                destination["chat_id"],
                payload["title"] + "\n" + payload["body"] + "\n" + payload["url"],
            )
        else:
            del payload["url"]
            web_push(
                destination, json.dumps(payload, ensure_ascii=False), environment, ttl
            )
    except TransportError as caught:
        error = caught
    except Exception:  # noqa: BLE001 — transport bodies and credentials must stay private.
        error = TransportError("DELIVERY_UNAVAILABLE", retry=30)
    with factory() as db:
        finish(db, key, token, clock(), error)
    return True


def recent_status(db):
    counts = {channel: {} for channel in CHANNELS}
    for channel, state, count in db.execute(
        select(ChannelDelivery.channel, ChannelDelivery.status, func.count()).group_by(
            ChannelDelivery.channel,
            ChannelDelivery.status,
        )
    ):
        counts[channel][state] = count
    return counts


def prune(db, now):
    with writer(db):
        db.execute(
            delete(ChannelDelivery).where(ChannelDelivery.created < now - 30 * 86400)
        )
        db.execute(
            delete(DeliveryTarget).where(
                DeliveryTarget.active.is_(False),
                DeliveryTarget.since < now - 30 * 86400,
            )
        )
