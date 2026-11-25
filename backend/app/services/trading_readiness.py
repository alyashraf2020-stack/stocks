"""Evidence-based readiness. The release has no commissioned write transport."""

from datetime import timedelta

from sqlalchemy import func, select

from app.models.backtest_run import SimulationDataset
from app.models.delivery import DeliveryTarget, WorkerPulse
from app.models.paper_trade import PaperTrade
from app.models.scheduled_job import ScannerHeartbeat
from app.schemas.trading_readiness import Check
from app.services.notification_delivery import configuration, env, prefs
from app.services.order_reconciliation import capabilities
from app.services.order_validation import BUY
from app.services.portfolio_risk import fees_configured
from app.services.scanner_calendar import calendar_at


def readiness(db, clock, connection, policy, *, draft=None, https=False):
    declared = capabilities(connection)
    market = calendar_at(clock)
    checks = []

    def add(code, status, evidence, action, mandatory=True):
        checks.append(
            Check(
                code=code,
                status=status,
                evidence=evidence,
                action=action,
                checked_at=clock,
                mandatory=mandatory,
            )
        )

    connected = connection.status == "CONNECTED"
    details = draft or {}
    intent = details.get("intent")
    buy = intent in BUY
    add(
        "THNDR_AUTHORIZATION",
        "PASS" if connected else "UNKNOWN",
        connection.status,
        "اربط حسابك للقراءة من صفحة تكامل ثاندر. حالة الاتصال من الخزنة المحلية.",
    )
    add(
        "THNDR_PROPOSAL_GRANT",
        "FAIL" if connected else "UNKNOWN",
        declared["proposal_grant"],
        "اطلب من ثاندر تأكيد إتاحة الميزة لحسابك وتصريح مستقل لها.",
    )
    add(
        "OFFICIAL_TOOL_SCHEMA",
        "UNKNOWN",
        "PUBLIC_TOOL_NAMES_ONLY",
        "اطلب مخططات الطلب والرد والتسوية ومواصفات منع التكرار للحساب والعميل.",
    )
    add(
        "LICENSED_LIVE_FEED",
        "UNKNOWN",
        "NO_COMMISSIONED_PROVIDER",
        "فعّل تغذية EGX مرخّصة مع دليل الاستحقاق والهوية وتوقيت المصدر.",
    )
    add(
        "REALTIME_QUOTE",
        "FAIL"
        if details.get("freshness") in {"DELAYED", "HISTORICAL", "MANUAL", "STALE"}
        else "UNKNOWN",
        details.get("freshness") or "NO_VERIFIED_OBSERVATION",
        "راجع مصدر السعر ووقته. لازم سعر لحظي متحقق منه.",
    )
    add(
        "INSTRUMENT",
        "PASS"
        if details.get("isin") and details.get("listing") == "ACTIVE"
        else "UNKNOWN",
        details.get("isin") or "NO_VERIFIED_ISIN",
        "طابق الرمز والـISIN وحالة القيد لدى مصدر السوق.",
    )
    add(
        "CALENDAR",
        "PASS" if market["completed_session"] else "UNKNOWN",
        market["version"],
        "راجع تغطية تقويم البورصة وحدّث الإجازات والجلسات الخاصة.",
    )
    add(
        "OPEN_MARKET",
        "FAIL"
        if market["session_status"] in {"CLOSED", "HALTED", "PRE_MARKET"}
        else "UNKNOWN",
        market["session_status"],
        "أكد من مصدر مستقل حالة السوق وإيقاف التداول على الأداة.",
    )
    sync_age = (
        clock - connection.last_sync
        if connection.last_sync and connection.last_sync.tzinfo
        else None
    )
    current_snapshot = bool(
        connected
        and sync_age is not None
        and timedelta(0) <= sync_age <= timedelta(minutes=policy.max_snapshot_minutes)
    )
    add(
        "PORTFOLIO",
        "PASS" if current_snapshot else "UNKNOWN",
        connection.last_sync.isoformat()
        if connection.last_sync
        else "NO_AUTHORIZED_SNAPSHOT",
        "زامن محفظة ثاندر بعد تأكيد الإذن.",
    )
    add(
        "SETTLEMENT",
        "UNKNOWN",
        "BROKER_SETTLEMENT_FIELDS_UNVERIFIED",
        "وثّق النقد المسوّى والقوة الشرائية والكمية المتاحة للبيع.",
    )
    add(
        "PENDING_ORDERS",
        "UNKNOWN",
        "RESERVED_CASH_AND_SHARES_NOT_VERIFIED",
        "راجع أوامر الوسيط المفتوحة وقيم النقد والأسهم المحجوزة.",
    )
    add(
        "PRICE_RULES",
        "UNKNOWN",
        "NO_VERIFIED_DAILY_TICK_AND_BOUNDS",
        "وثّق وحدة السعر وحدود التداول لكل سهم وجلسة.",
    )
    add(
        "FEES",
        "UNKNOWN",
        "LOCAL_ESTIMATE_CONFIGURED"
        if fees_configured(policy)
        else "FEE_INPUTS_MISSING",
        "سجّل الرسوم والضرائب الفعلية للأمر من مصدر وسيط معتمد.",
    )
    add(
        "RISK_POLICY",
        "PASS",
        "DETERMINISTIC_CAPS_1_5_AND_20",
        "راجع الحدود الأكثر تحفظًا وإعدادات المخاطر المتقدمة.",
    )
    add(
        "ORDER_RISK",
        "FAIL" if details.get("scenario_blockers") else "UNKNOWN",
        "، ".join(details.get("scenario_blockers") or [])
        or "COMPLETE_BROKER_RISK_INPUTS_REQUIRED",
        "استكمل السيولة والتعرّض والحجم وحساب المخاطر باستخدام لقطة مصرح بيها.",
    )
    if policy.islamic_mode and (not intent or buy):
        screening = details.get("sharia")
        add(
            "SHARIA",
            "PASS"
            if screening == "COMPLIANT"
            else "FAIL"
            if screening == "NON_COMPLIANT"
            else "UNKNOWN",
            screening or "SCREENING_EVIDENCE_MISSING",
            "راجع أدلة الفرز الموثقة والمتاحة وقت المراجعة.",
        )
    else:
        add(
            "SHARIA",
            "NOT_APPLICABLE",
            "ENTRY_SCREENING_NOT_APPLICABLE",
            "وضع الخروج يفضل متاح للمراجعة.",
        )
    emergency_status = "FAIL" if policy.kill_switch and (buy or not intent) else "PASS"
    add(
        "EMERGENCY_STOP",
        emergency_status,
        "ACTIVE" if policy.kill_switch else "INACTIVE",
        "راجع مفتاح الإيقاف في المخاطر. المراجعات بهدف خفض المخاطر تفضل متاحة.",
    )
    count_data = db.scalar(
        select(func.count())
        .select_from(SimulationDataset)
        .where(SimulationDataset.data["kind"].as_string() == "EQUITY")
    )
    add(
        "HISTORICAL_DATA",
        "UNKNOWN" if count_data else "FAIL",
        f"DATASET_VERSIONS:{count_data}",
        "استورد حزم أسعار مصرّح بيها وتأكد من أنها تغطي نافذة التحقق المحددة.",
    )
    fills = db.scalar(select(func.count()).select_from(PaperTrade))
    add(
        "PAPER_VALIDATION",
        "UNKNOWN",
        f"VIRTUAL_FILLS:{fills}",
        "شغّل محاكاة على بيانات مرخصة وسجّل معايير نجاح ونتيجة راجعها المالك.",
    )
    add(
        "STRATEGY_VALIDATION",
        "UNKNOWN",
        "PROFITABILITY_UNVERIFIED",
        "وثّق التحقق بعد الرسوم والانزلاق وخارج العينة.",
    )
    add(
        "OWNER_COMMISSIONING",
        "UNKNOWN",
        "NO_INDEPENDENT_COMMISSIONING_EVIDENCE",
        "اعتمد الإعداد بعد استيفاء الأدلة. اختيار وضع المراجعة وحده غير كافٍ.",
    )
    add(
        "RELEASE_GATE",
        "FAIL",
        "LIVE_CAPABILITY_DISABLED",
        "استخدم المراجعة اليدوية. الإصدار الحالي مخصص للمسودات.",
    )
    add(
        "HTTPS",
        "PASS" if https else "UNKNOWN",
        "AUTHENTICATED_HTTPS_INGRESS" if https else "HTTPS_NOT_OBSERVED",
        "افتح من بوابة المالك HTTPS.",
    )
    latest = db.scalar(select(func.max(ScannerHeartbeat.seen)))
    pulse = db.get(WorkerPulse, "notifications")
    settings = prefs(db)
    configured = configuration(env())
    targets = list(
        db.scalars(select(DeliveryTarget).where(DeliveryTarget.active.is_(True)))
    )
    active = any(
        configured[target.channel]
        and getattr(settings, "telegram" if target.channel == "TELEGRAM" else "push")
        for target in targets
    )
    add(
        "WORKERS",
        "PASS" if latest and 0 <= clock.timestamp() - latest <= 30 else "UNKNOWN",
        "SCANNER_HEARTBEAT",
        "راجع آخر نبضة من صفحة النظام.",
        False,
    )
    delivered = any(target.last_ok for target in targets)
    add(
        "NOTIFICATIONS",
        "PASS"
        if active and delivered and pulse and 0 <= clock.timestamp() - pulse.seen <= 40
        else "UNKNOWN",
        "DELIVERY_AND_HEARTBEAT_REQUIRED",
        "اربط جهاز أو تيليجرام واختبر الإرسال.",
        False,
    )
    return {
        "status": "READY"
        if all(x.status in {"PASS", "NOT_APPLICABLE"} for x in checks if x.mandatory)
        else "BLOCKED",
        "broker_handoff": False,
        "capabilities": declared,
        "checks": checks,
        "market": market,
    }
