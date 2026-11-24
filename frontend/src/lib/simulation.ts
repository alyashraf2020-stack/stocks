export const strategies: Record<string, string> = {
  EGX26: "EGX26", PULLBACK: "الارتداد", BREAKOUT: "الاختراق", TREND: "متابعة الاتجاه", COMBINED: "الاستراتيجية المجمّعة",
};
export const simulationStatus: Record<string, string> = {
  PENDING: "في الانتظار", ACCEPTED: "مقبول افتراضيًا", PARTIALLY_FILLED: "تنفيذ جزئي",
  FILLED: "اتنفّذ افتراضيًا", CANCELLED: "اتلغى", EXPIRED: "انتهت الصلاحية", REJECTED: "مرفوض",
  RUNNING: "جاري التشغيل", SUCCEEDED: "اكتمل", FAILED: "تعذّر التشغيل",
};
export const simulationReason: Record<string, string> = {
  DATA_UNAVAILABLE: "بيانات معتمدة غير متاحة",
  VERIFIED_CURRENT_EOD_REQUIRED: "بيانات آخر جلسة المكتملة مطلوبة",
  UNKNOWN_APPROVED_DATASET: "اختار حزمة بيانات معتمدة",
  INSTRUMENT_IDENTITY_UNVERIFIED: "هوية الورقة المالية غير مؤكدة",
  VERIFIED_TICK_AND_DAILY_BOUNDS_REQUIRED: "وحدة السعر وحدود الجلسة مطلوبة",
  KILL_SWITCH: "الإيقاف الطارئ شغّال",
  SHARIA_ENTRY_BLOCKED: "الشراء الافتراضي محجوب بالفحص الشرعي",
  INSUFFICIENT_SETTLED_CASH: "الرصيد الافتراضي المسوّى غير كافٍ",
  INSUFFICIENT_UNRESERVED_SHARES: "الأسهم الافتراضية المتاحة غير كافية",
  ACCOUNT_RECONCILIATION_REQUIRED: "استنى العامل يراجع آخر جلسة مكتملة",
  CALENDAR_COVERAGE_REQUIRED: "الجلسة خارج نطاق التقويم المعتمد",
  COMPLETED_CALENDAR_RANGE_REQUIRED: "اختار فترة مكتملة ضمن نطاق التقويم",
  BACKTEST_SCOPE_TOO_LARGE: "قلّل عدد الأسهم أو الاستراتيجيات أو طول الفترة",
  INSUFFICIENT_WARMUP: "تاريخ متصل أقل من 200 جلسة",
  POINT_IN_TIME_SCREENING_MISSING_OR_INELIGIBLE: "الفحص الشرعي المتاح وقت القرار غير كافٍ لبعض الأسهم",
  STOP_LOSS: "وقف الخسارة الافتراضي", TAKE_PROFIT: "جني الربح الافتراضي",
  TECHNICAL_EXIT: "خروج بسبب تغيّر القراءة الفنية", MAX_HOLDING_PERIOD: "وصل لحد مدة الاحتفاظ",
  OWNER_CANCELLED: "إلغاء المالك", ORDER_WINDOW_ENDED: "انتهت فترة الأمر",
  BENCHMARK_DATES_NOT_ALIGNED: "تواريخ المؤشر مش مطابقة لجلسات الاختبار",
};

type MaybeNumber = string | number | null | undefined;
export interface Dataset {
  id: string; ticker: string; source: string; kind: string; bars: number; first_session: string; last_session: string; digest: string;
}
export interface Point { day: string; equity: MaybeNumber; nav?: MaybeNumber; }
export interface Run {
  id: string; status: string; progress: number; start: string; end: string; strategies: string[];
  error: string | null;
}
export interface Trade {
  order_id: string; side: string; ticker: string; trade_session: string; price: MaybeNumber;
  shares: number; fees: MaybeNumber; tax: MaybeNumber; realized: MaybeNumber; reason: string; scenario?: string;
}
export function display(value: MaybeNumber, percentage = false) {
  if (value == null || !Number.isFinite(Number(value))) return "غير متاح";
  return new Intl.NumberFormat("ar-EG", {
    ...(percentage ? { style: "percent" } : {}), maximumFractionDigits: percentage ? 2 : 4,
  }).format(Number(value));
}

export async function simulationRequest<T>(path: string, body?: object): Promise<T> {
  const response = await fetch("/api/v1/" + path, {
    cache: "no-store", credentials: "same-origin",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 403) throw new Error("افتح التطبيق من بوابة HTTPS الخاصة بالمالك.");
    const detail = typeof payload?.detail === "string" ? payload.detail : "";
    throw new Error(simulationReason[detail] ?? (detail || "راجع القيم المدخلة وحالة البيانات."));
  }
  return payload as T;
}
