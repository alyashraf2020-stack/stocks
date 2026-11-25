export const opsPanel = "space-y-4 rounded-2xl border border-surfaceBorder bg-surface p-4 sm:p-5";
export const opsField = "min-h-11 w-full rounded-xl border border-surfaceBorder bg-background px-3 py-2 text-gray-100";
export const opsButton = "min-h-11 rounded-xl bg-primary px-4 py-2 font-bold text-background disabled:opacity-50";
export const opsOutline = "min-h-11 rounded-xl border border-surfaceBorder px-4 py-2 text-primary disabled:opacity-50";

export const alertCategories: Record<string, string> = {
  BUY_REVIEW: "فرصة شراء للمراجعة", SELL_REVIEW: "مركز يحتاج مراجعة", ENTRY_ZONE: "تغيّر نطاق الدخول",
  BREAKOUT: "إشارة اختراق", RATING_CHANGE: "التقييم الفني اتغيّر", STOP: "رصد الوقف", TARGET: "رصد الهدف",
  PORTFOLIO_RISK: "مخاطر المحفظة", SHARIA_CHANGE: "تغيّر الفحص الشرعي", MARKET_DATA: "بيانات السوق",
  THNDR_CONNECTION: "اتصال ثاندر", SCANNER_FAILURE: "حالة الماسح", KILL_SWITCH: "الإيقاف الطارئ",
  TECHNICAL_CHANGE: "تغيّر فني", PAPER_FILL: "تنفيذ افتراضي", PAPER_REJECTED: "أمر افتراضي مرفوض",
  BACKTEST_COMPLETED: "اختبار تاريخي مكتمل", BACKTEST_FAILED: "اختبار تاريخي تعذّر",
};
const labels: Record<string, string> = {
  NOT_CONFIGURED: "غير مهيأ", CONFIGURED: "مهيأ", CONNECTED: "متصل", RUNNING: "شغّال",
  DISCONNECTED: "غير متصل", DEGRADED: "يحتاج مراجعة", UNAVAILABLE: "غير متاح",
  RECHECK_REQUIRED: "تحتاج تحديث قبل المراجعة", RISK_BLOCKED: "محجوبة بالمخاطر",
  SHARIA_BLOCKED: "محجوبة بالفحص الشرعي", HOLDING_REVIEW: "مركز يحتاج مراجعة",
  ENTRY_WATCH: "نطاق دخول للمراجعة", UNKNOWN: "غير متحقق منه", HISTORICAL: "تاريخي", DELAYED: "متأخر",
  DELIVERED: "اترسل", FAILED: "فشل", PENDING: "في الانتظار", SENDING: "جاري الإرسال",
  SUPPRESSED: "اتوقف حسب الإعدادات", EXPIRED: "انتهت الصلاحية", SUCCEEDED: "اكتمل", CANCELLED: "اتلغى",
  APPROVED: "صالح حسب الحزمة", APPROVED_PARTIAL: "صالح مع تغطية جزئية", DUPLICATE: "نسخة موجودة",
  REJECTED: "مرفوض", QUOTA: "وصل للحد اليومي", PAIR_EXPIRED: "ابدأ ربط جديد. الربط انتهت صلاحيته.",
  PAIR_RATE_LIMITED: "استنى شوية قبل إعادة التحقق.", TELEGRAM_CREDENTIALS_INVALID: "بيانات البوت غير صالحة.",
  TELEGRAM_RATE_LIMITED: "تيليجرام طلب الانتظار قبل المحاولة التالية.", PUSH_ENDPOINT_UNSUPPORTED: "عنوان خدمة الإشعارات غير مدعوم.",
  PUSH_NOT_CONFIGURED: "إشعارات المتصفح محتاجة إعداد على الخادم.", DEVICE_EXPIRED: "اشتراك الجهاز انتهى.",
  SETTINGS_CHANGED: "الإعدادات اتغيرت. حدّث الصفحة وحاول تاني.",
  DESTINATION_NOT_AUTHORIZED: "الجهاز أو المحادثة محتاج ربط وتفعيل.",
  QUIET_HOURS_INVALID: "اختار بداية ونهاية مختلفتين لساعات الهدوء.",
  DELIVERY_TEST_RATE_LIMIT: "استنى دقيقة قبل طلب اختبار تاني.",
  DATA_UNAVAILABLE: "مفيش سعر جلسة متاح.", INSTRUMENT_ID_MISSING: "رمز ISIN ناقص في الدليل.",
  STALE_EOD: "السعر أقدم من آخر جلسة مكتملة.", ANALYSIS_WARMUP_MISSING: "عدد الشموع الصالحة غير كافٍ.",
  CORPORATE_ACTION_EVIDENCE_MISSING: "مراجعة إجراءات الشركة محتاجة إثبات من المصدر.",
  APPROVED_EXECUTION_DATA_MISSING: "استورد حزمة غير معدّلة بحدود السعر ووحدة التداول.",
  INVALID_SESSION_OR_AVAILABLE_TIMESTAMP: "راجع التقويم وتوقيت نشر الشمعة بعد الإغلاق.",
  INVALID_POINT_IN_TIME_EVENT: "راجع تاريخ إعلان الإجراء قبل وقت تطبيقه.",
  VERIFIED_TICK_AND_DAILY_BOUNDS_REQUIRED: "راجع وحدة التداول والحد الأدنى والأقصى للسعر لكل صف.",
  IMPORT_DAILY_QUOTA: "الاستيراد وصل للحد اليومي.",
  CSV_REQUIRED_COLUMNS_MISSING: "أعمدة أساسية ناقصة أو الربط مختلف عن الملف.",
  CSV_ROW_SHAPE_INVALID: "عدد خلايا صف مختلف عن العناوين أو الملف تخطى 420 صف.",
  DATASET_SCHEMA_INVALID: "في حقول محتاجة تصحيح.", JSON_INVALID: "صيغة JSON غير صالحة.",
  INSTRUMENT_IDENTITY_UNVERIFIED: "الرمز وISIN لازم يطابقوا دليل الأدوات.",
};

export function label(code?: string | null) {
  return code ? labels[code] ?? alertCategories[code] ?? code : "غير متاح";
}
export function timeLabel(value?: string | number | null) {
  if (!value) return "غير متاح";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("ar-EG", {
    timeZone: "Africa/Cairo", dateStyle: "medium", timeStyle: "short",
  }) : "غير متاح";
}
export function numberLabel(value?: number | string | null) {
  return value == null ? "غير متاح" : new Intl.NumberFormat("ar-EG", {maximumFractionDigits: 2}).format(Number(value));
}
export async function ops<T>(path: string, body?: object): Promise<T> {
  const response = await fetch("/api/v1/" + path, {
    cache: "no-store", credentials: "same-origin",
    ...(body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {}),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error("افتح التطبيق من بوابة HTTPS الخاصة بالمالك.");
    throw new Error(typeof data?.detail === "string" ? label(data.detail) : "راجع البيانات أو جرّب تاني بعد شوية.");
  }
  return data as T;
}
