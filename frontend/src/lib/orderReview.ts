import { label } from "@/lib/operations";

export const intents: Record<string, string> = {
  BUY: "شراء جديد", ADD: "إضافة لمركز", PARTIAL_SELL: "بيع جزئي", FULL_EXIT: "خروج كامل",
  TAKE_PROFIT: "جني ربح جزئي", STOP_REVIEW: "مراجعة وقف الخسارة",
};
export const states: Record<string, string> = {
  DRAFT: "مسودة", BLOCKED: "الإرسال الرسمي محجوب", APPROVAL_REQUIRED: "في انتظار تأكيد المراجعة",
  LOCAL_REVIEWED: "اتأكدت المراجعة محليًا", INVALIDATED: "اتلغت صلاحية النسخة", EXPIRED: "انتهت المدة",
  CANCELLED: "المسودة مرفوضة", REVIEW_CHALLENGE_REPLACED: "رمز مراجعة جديد",
  NOT_SUBMITTED: "لم تُرسل للوسيط", UNKNOWN: "غير متاح", PASS: "متحقق", FAIL: "غير مستوفى",
  NOT_APPLICABLE: "لا ينطبق", LIVE_CAPABILITY_DISABLED: "الإرسال الرسمي غير متاح في الإصدار الحالي",
  LOCAL_REVIEW_ONLY: "مراجعة محلية فقط", HISTORICAL: "سعر جلسة تاريخي", MANUAL: "مدخل يدوي",
  DELAYED: "سعر متأخر", STALE: "سعر قديم", REALTIME_VERIFIED: "سعر لحظي متحقق منه",
};
export const checks: Record<string, string> = {
  THNDR_AUTHORIZATION: "اتصال ثاندر", THNDR_PROPOSAL_GRANT: "إذن اقتراح الأوامر",
  OFFICIAL_TOOL_SCHEMA: "مخطط أدوات ثاندر", LICENSED_LIVE_FEED: "ترخيص الأسعار اللحظية",
  REALTIME_QUOTE: "حداثة السعر", INSTRUMENT: "هوية الأداة المالية", CALENDAR: "التقويم",
  OPEN_MARKET: "حالة السوق والتداول", PORTFOLIO: "حداثة لقطة المحفظة",
  SETTLEMENT: "النقد والأسهم المسوّاة", PENDING_ORDERS: "الأوامر القائمة والحجوزات",
  PRICE_RULES: "وحدة السعر والحدود اليومية", FEES: "العمولات والضرائب",
  RISK_POLICY: "سياسة المخاطر", ORDER_RISK: "مخاطر الصفقة والسيولة", SHARIA: "الفحص الشرعي",
  EMERGENCY_STOP: "الإيقاف الطارئ", HISTORICAL_DATA: "بيانات التنفيذ التاريخية",
  PAPER_VALIDATION: "التحقق بالتداول الافتراضي", STRATEGY_VALIDATION: "التحقق من الاستراتيجية بعد التكلفة",
  OWNER_COMMISSIONING: "اعتماد المالك المستقل", RELEASE_GATE: "قدرة الإصدار الحالي", HTTPS: "بوابة HTTPS",
  WORKERS: "نبضات التشغيل", NOTIFICATIONS: "قنوات الإشعار",
};
export const modeLabels: Record<string, string> = {
  ANALYSIS_ONLY: "تحليل فقط", PAPER_TRADING: "التداول الافتراضي", SEMI_AUTOMATIC_REVIEW: "مراجعة مسودات شبه آلية",
};
export function orderLabel(code?: string | null) {
  return code ? states[code] ?? label(code) : "غير متاح";
}
export const activeStates = ["BLOCKED", "APPROVAL_REQUIRED", "LOCAL_REVIEWED"];
