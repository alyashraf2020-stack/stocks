import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.core.database import Base, get_db
from app.integrations import web_push
from app.integrations.telegram_client import Telegram, TransportError
from app.main import app
from app.models.delivery import ChannelDelivery, DeliveryTarget
from app.models.notification import Notification
from app.models.security import EGXSecurity
from app.schemas.market_import import ImportEnvironment, ImportFile
from app.schemas.notification_settings import (
    DeliveryEnvironment,
    PushDevice,
)
from app.schemas.risk import RiskPolicy
from app.schemas.scanner import ScannerSettings
from app.services import market_import
from app.services import notification_delivery as outbox
from app.services.data_provider.manager import default_provider_manager
from app.services.notification_service import emit
from app.services.risk_policy import save_policy
from app.services.scanner_calendar import CAIRO, calendar_at
from app.services.scanner_repository import enqueue, save_settings, writer
from app.services.worker_pulse import pulse
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from pywebpush import WebPushException
from requests import Response
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 11, 23, 16, tzinfo=CAIRO)
CLOCK = NOW.timestamp()
TOKEN = "12345678:fake_telegram_token_for_testing_only"
MASTER = "EGS60201C018"


def encoded(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'operations.db'}")
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, autoflush=False)
    with make() as db:
        db.add(
            EGXSecurity(
                ticker="COMI",
                isin=MASTER,
                arabic_name="اختبار",
                english_name="Test",
                sector="Banks",
                listing_status="ACTIVE",
                source_updated_at="2026-11-23",
            )
        )
        db.execute(text("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)"))
        db.execute(
            text("INSERT INTO alembic_version VALUES ('0006_order_review')")
        )
        db.commit()
    yield make
    engine.dispose()


@pytest.fixture
def delivery(monkeypatch):
    key = generate_private_key(SECP256R1())
    conf = DeliveryEnvironment(
        TELEGRAM_ENABLED=True,
        TELEGRAM_BOT_TOKEN=TOKEN,
        APP_HOST="egx.example",
        WEB_PUSH_ENABLED=True,
        VAPID_SUBJECT="mailto:demo@example.org",
        VAPID_PRIVATE_KEY=encoded(
            key.private_numbers().private_value.to_bytes(32, "big")
        ),
        VAPID_PUBLIC_KEY=encoded(
            key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        ),
        NOTIFICATION_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(outbox, "env", lambda: conf)
    return conf


def device(label="Test"):
    key = generate_private_key(SECP256R1())
    return PushDevice(
        endpoint="https://fcm.googleapis.com/fcm/send/example_session",
        name=label,
        keys={
            "p256dh": encoded(
                key.public_key().public_bytes(
                    Encoding.X962, PublicFormat.UncompressedPoint
                )
            ),
            "auth": encoded(bytes(range(16))),
        },
    )


def options(factory, **settings):
    with factory() as db:
        current = outbox.prefs(db)
        db.rollback()
        return outbox.set_prefs(db, current.model_copy(update=settings), CLOCK - 20)


def register(factory, environment):
    sub = device()
    with factory() as db, writer(db):
        tg = outbox.install_target(
            db,
            "TELEGRAM",
            "Owner",
            "owner",
            {"chat_id": 15, "bot_key": outbox.digest(environment.TELEGRAM_BOT_TOKEN)},
            CLOCK - 10,
            environment,
        )
        push = outbox.install_target(
            db,
            "PUSH",
            sub.name,
            sub.endpoint,
            sub.model_dump(exclude={"name"}),
            CLOCK - 10,
            environment,
        )
    return tg, push


def note(factory, *, now=CLOCK, severity="WARNING", category="MARKET_DATA", data=None):
    with factory() as db, writer(db):
        emit(
            db,
            ScannerSettings(),
            now,
            category,
            severity,
            {"reason": "DATA_UNAVAILABLE", **(data or {})},
            f"fixture:{now}:{category}",
        )


def test_telegram_valid_pair_unauthorized_chat_and_expiry(
    factory, delivery, monkeypatch
):
    class FakeBot:
        def __init__(self, token):
            assert token == TOKEN

        def bot(self):
            return "fixture_bot"

        def updates(self):
            return updates

    monkeypatch.setattr(outbox, "Telegram", FakeBot)
    monkeypatch.setattr(outbox.time, "time", lambda: CLOCK + 6)
    with factory() as db:
        paired = outbox.pair_start(db, CLOCK, delivery)
    code = parse_qs(urlsplit(paired["url"]).query)["start"][0]
    model = {
        "text": "/start " + code,
        "date": int(CLOCK + 1),
        "chat": {"id": 15, "type": "private"},
        "from": {"id": 15},
    }
    updates = [{"message": {**model, "chat": {"type": "group", "id": 15}}}]
    assert outbox.pair_check(factory, CLOCK + 2, delivery) == {"paired": False}
    updates = [{"message": model}]
    with pytest.raises(ValueError, match="PAIR_RATE_LIMITED"):
        outbox.pair_check(factory, CLOCK + 3, delivery)
    assert (
        outbox.paired_chat(
            updates, outbox.digest(code), CLOCK + 600, CLOCK + 3, owner_id=999
        )
        is None
    )
    assert outbox.pair_check(factory, CLOCK + 6, delivery) == {"paired": True}
    with factory() as db:
        target = db.scalar(select(DeliveryTarget))
        assert (
            target.active and code not in target.secret and TOKEN not in target.secret
        )
        assert outbox.decrypt(delivery, target.secret)["chat_id"] == 15
    with pytest.raises(ValueError, match="PAIR_EXPIRED"):
        outbox.pair_check(factory, CLOCK + 10, delivery)


@pytest.mark.parametrize(
    ("status", "data", "code"),
    [
        (401, {"ok": False}, "TELEGRAM_CREDENTIALS_INVALID"),
        (
            429,
            {"ok": False, "parameters": {"retry_after": 48}},
            "TELEGRAM_RATE_LIMITED",
        ),
        (503, {"ok": False}, "TELEGRAM_UNAVAILABLE"),
    ],
)
def test_telegram_transport_errors_redact_token(status, data, code, caplog):
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=data))
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(TransportError) as failure,
    ):
        Telegram(TOKEN, client=client).deliver(15, "safe")
    assert failure.value.code == code and TOKEN not in caplog.text
    if status == 429:
        assert failure.value.retry == 48


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/fcm/path",
        "https://[::1]/fcm/path",
        "https://169.254.169.254/latest/meta-data",
        "http://fcm.googleapis.com/fcm/path",
        "https://fcm.googleapis.com:8443/fcm/path",
        "https://fcm.googleapis.com@evil.example/fcm/path",
        "https://fcm.googleapis.com.bad.example/fcm/path",
        "https://fcm.googleapis.com/fcm/path?redirect=https://localhost",
        "https://fcm.googleapis.com/%2e%2e/private",
        "https://fcm.googleapis.com/fcm/path\n",
        "https://push.apple.com.evil.example/opaque",
    ],
)
def test_push_ssrf_rejected(url):
    assert not web_push.endpoint_allowed(url)
    with (
        web_push.DirectSession() as session,
        pytest.raises(TransportError, match="PUSH_ENDPOINT_UNSUPPORTED"),
    ):
        session.post(url, timeout=0.1)


def test_push_subscription_and_expired_device(factory, delivery, monkeypatch):
    options(factory, push=True)
    _, key = register(factory, delivery)
    sub = device()
    web_push.validate_device(sub)
    note(factory)
    observed = []

    def failed(**args):
        observed.append(args["subscription_info"]["endpoint"])
        response = Response()
        response.status_code = 410
        raise WebPushException("provider payload must stay private", response=response)

    monkeypatch.setattr(web_push, "webpush", failed)
    assert outbox.delivery_step(factory, "PUSH", lambda: CLOCK + 1, delivery)
    assert observed == [sub.endpoint]
    with factory() as db:
        target = db.get(DeliveryTarget, key)
        row = db.scalar(select(ChannelDelivery))
        assert not target.active and target.secret == ""
        assert row.error == "DEVICE_EXPIRED" and row.status == "FAILED"


def test_independent_queues_concurrent_leases_backoff_and_recovery(factory, delivery):
    options(factory, telegram=True, push=True)
    register(factory, delivery)
    note(factory)

    def competing(_):
        with factory() as db:
            return outbox.claim(db, "TELEGRAM", CLOCK + 1, delivery)

    with ThreadPoolExecutor(max_workers=6) as pool:
        received = [item for item in pool.map(competing, range(6)) if item]
    assert len(received) == 1
    old = received[0]
    with factory() as db:
        push = outbox.claim(db, "PUSH", CLOCK + 1, delivery)
        assert outbox.finish(db, push[0], push[1], CLOCK + 2)
    expired = CLOCK + outbox.LEASE + 2
    with factory() as db:
        regained = outbox.claim(db, "TELEGRAM", expired, delivery)
        assert regained[0] == old[0] and regained[1] != old[1]
        assert not outbox.finish(db, old[0], old[1], expired)
        assert outbox.finish(
            db,
            regained[0],
            regained[1],
            expired,
            TransportError("TELEGRAM_RATE_LIMITED", retry=200),
        )
        assert outbox.claim(db, "TELEGRAM", expired + 100, delivery) is None
        assert outbox.claim(db, "TELEGRAM", expired + 201, delivery) is not None


def test_opt_in_revocation_and_expired_delivery(factory, delivery):
    tg, _ = register(factory, delivery)
    note(factory)
    with factory() as db:
        assert list(db.scalars(select(ChannelDelivery))) == []
    options(factory, telegram=True)
    note(factory, now=CLOCK + 21610)
    with factory() as db:
        assert outbox.revoke(db, tg)
        assert outbox.claim(db, "TELEGRAM", CLOCK + 21611, delivery) is None
        assert db.scalar(select(ChannelDelivery)).status == "SUPPRESSED"
    register(factory, delivery)
    note(factory, now=CLOCK + 43230)
    with factory() as db:
        assert outbox.claim(db, "TELEGRAM", CLOCK + 43231 + 7 * 86400, delivery) is None
        assert any(
            row.status == "EXPIRED" for row in db.scalars(select(ChannelDelivery))
        )


def test_quiet_hours_privacy_and_emergency_revalidation(factory, delivery):
    options(factory, telegram=True, push=True, quiet_start=22 * 60, quiet_end=6 * 60)
    register(factory, delivery)
    assert outbox.quiet(
        outbox.DeliveryPreferences(quiet_start=22 * 60, quiet_end=6 * 60),
        NOW.replace(hour=23).timestamp(),
        "CRITICAL",
    )
    assert not outbox.quiet(
        outbox.DeliveryPreferences(
            quiet_start=22 * 60, quiet_end=6 * 60, critical_bypass=True
        ),
        NOW.replace(hour=23).timestamp(),
        "CRITICAL",
    )
    note(
        factory,
        severity="OPPORTUNITY",
        category="BUY_REVIEW",
        data={
            "ticker": "COMI",
            "_instrument": MASTER,
            "_ref_session": NOW.date().isoformat(),
            "_signal_expires": (NOW + timedelta(minutes=25)).isoformat(),
            "freshness": "HISTORICAL",
            "source_timestamp": NOW.isoformat(),
            "account_balance": "private-number",
            "credential": "secret",
        },
    )
    with factory() as db:
        notice = db.scalar(select(Notification))
        generic = json.dumps(
            outbox.redact(notice, False, "egx.example"), ensure_ascii=False
        )
        detail = json.dumps(
            outbox.redact(notice, True, "egx.example"), ensure_ascii=False
        )
        assert "COMI" not in generic and "COMI" in detail
        assert "secret" not in detail and "private-number" not in detail
        assert outbox.opportunity_current(db, notice, CLOCK + 1)
        save_policy(db, RiskPolicy(kill_switch=True))
    with factory() as db:
        assert outbox.claim(db, "TELEGRAM", CLOCK + 2, delivery) is None
        assert (
            db.scalar(
                select(ChannelDelivery).where(ChannelDelivery.channel == "TELEGRAM")
            ).status
            == "SUPPRESSED"
        )


def bundle():
    from tests.test_paper_backtesting import data

    value = data().model_dump(mode="json")
    value["bars"] = [
        bar for bar in value["bars"] if bar["day"] <= NOW.date().isoformat()
    ]
    value["last_session"] = NOW.date().isoformat()
    return value


def test_market_csv_preview_partial_dedup_preservation_and_late_scanner(factory):
    value = bundle()
    value["first_session"] = "2026-11-19"
    valid = next(x for x in value["bars"] if x["day"] == NOW.date().isoformat())
    value.pop("bars")
    value["source"] = "Authorized CSV test"
    csv = "date,seen,o,h,l,c,v,tick,lower_limit,upper_limit\n" + ",".join(
        str(valid[key])
        for key in (
            "day",
            "available_at",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "tick",
            "lower_limit",
            "upper_limit",
        )
    )
    request = ImportFile(
        format="CSV",
        content=csv,
        metadata=value,
        mapping={
            "day": "date",
            "available_at": "seen",
            "open": "o",
            "high": "h",
            "low": "l",
            "close": "c",
            "volume": "v",
        },
    )
    with factory() as db:
        save_settings(db, ScannerSettings(enabled=True))
        early = enqueue(db, calendar_at(NOW), CLOCK)
    with factory() as db:
        _, report = market_import.inspect_bundle(db, request, NOW)
        assert report["valid"] and report["partial"] and report["bars"] == 1
    with factory() as db:
        receipt = market_import.persist(db, request, NOW, "MANUAL")
        assert receipt["status"] == "APPROVED_PARTIAL"
        assert market_import.persist(db, request, NOW, "MANUAL")["duplicate"]
        late = enqueue(db, calendar_at(NOW), CLOCK + 3)
        assert late != early and enqueue(db, calendar_at(NOW), CLOCK + 4) == late
    with factory() as db:
        latest = default_provider_manager.get_analytical_bars(
            "COMI", db=db, allow_network=False, completed_session=NOW.date()
        )
        assert latest["latest_session"] == NOW.date().isoformat()
        assert (
            latest["analytical_bars_count"] == 1
            and not latest["current_analysis_eligible"]
        )


@pytest.mark.parametrize(
    ("format", "content", "failure"),
    [
        ("JSON", "{bad}", "JSON_INVALID"),
        ("JSON", "[]", "JSON_OBJECT_REQUIRED"),
        ("CSV", "day,date\n2026-11-23,2026-11-23", "CSV_REQUIRED_COLUMNS_MISSING"),
    ],
)
def test_invalid_files_failure_history_and_quota(factory, format, content, failure):
    settings = ImportEnvironment(EOD_IMPORT_MAX_PER_DAY=1)
    with factory() as db:
        receipt = market_import.persist(
            db, ImportFile(format=format, content=content), NOW, "INBOX", settings
        )
        assert receipt["status"] == "REJECTED" and receipt["report"]["error"] == failure
        blocked = market_import.persist(
            db,
            ImportFile(format="JSON", content='{"next":true}'),
            NOW,
            "INBOX",
            settings,
        )
        assert blocked["status"] == "QUOTA"


def test_library_json_import_missing_tick_is_rejected_and_does_not_count(factory):
    value = bundle()
    value["bars"][-1]["tick"] = None
    with factory() as db:
        receipt = market_import.persist(
            db, ImportFile(format="JSON", content=json.dumps(value)), NOW, "MANUAL"
        )
        assert receipt["status"] == "REJECTED"
        assert receipt["report"]["error"] == "VERIFIED_TICK_AND_DAILY_BOUNDS_REQUIRED"


def test_authorization_and_worker_health(factory, delivery, monkeypatch, tmp_path):
    from app.api.v1.endpoints import system

    gateway = "long-gateway-key-for-phase-seven-testing"
    monkeypatch.setenv("INTEGRATIONS_GATEWAY_SECRET", gateway)
    monkeypatch.setenv("AI_LEDGER_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(system, "env", lambda: delivery)
    pulse(factory, "notifications")
    pulse(factory, "paper", now=1)

    def provide():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = provide
    try:
        client = TestClient(app)
        for route in ("system", "data", "notification-settings"):
            assert client.get("/api/v1/" + route).status_code == 403
        result = client.get("/api/v1/system", headers={"X-EGX-Gateway": gateway})
        values = result.json()
        assert values["workers"]["notifications"]["running"]
        assert not values["workers"]["paper"]["running"]
        assert values["migration"]["ready"]
        assert (
            TOKEN not in result.text
            and delivery.NOTIFICATION_ENCRYPTION_KEY not in result.text
        )
        details = client.get(
            "/api/v1/notification-settings", headers={"X-EGX-Gateway": gateway}
        )
        assert (
            details.status_code == 200
            and TOKEN not in details.text
            and delivery.VAPID_PRIVATE_KEY not in details.text
        )
    finally:
        app.dependency_overrides.pop(get_db)


def test_public_private_vapid_match_and_http_redirects_disabled(delivery, monkeypatch):
    import requests

    assert outbox.configuration(delivery)["PUSH"]
    broken = delivery.model_copy(update={"VAPID_PRIVATE_KEY": "A" * 43})
    assert not outbox.configuration(broken)["PUSH"]
    attempted = []
    monkeypatch.setattr(
        requests.Session,
        "request",
        lambda self, method, url, **kwargs: attempted.append(kwargs),
    )
    with web_push.DirectSession() as session:
        session.post(device().endpoint, allow_redirects=True)
    assert attempted[0]["allow_redirects"] is False
