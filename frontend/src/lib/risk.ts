export type Numeric = number | string | null;
export type Policy = {
  advanced_enabled: boolean;
  islamic_mode: boolean;
  kill_switch: boolean;
} & Record<string, Numeric | boolean>;
export type Screen = {
  ticker: string;
  company: string;
  sector: string;
  status: "COMPLIANT" | "NON_COMPLIANT" | "UNVERIFIED";
  reasons: string[];
  ratios: Record<string, Numeric>;
  limits: Record<string, Numeric>;
  evidence: {
    reviewed_on: string;
    period_end: string | null;
    activity_source: string;
    financial_source: string | null;
    index_member: boolean | null;
    index_as_of: string | null;
    index_source: string | null;
    market_value_source: string | null;
  } | null;
};

export const screenLabels = {
  COMPLIANT: "مستوفٍ للضوابط",
  NON_COMPLIANT: "غير مستوفٍ",
  UNVERIFIED: "غير متحقق منه",
};
export const ratiosAr: Record<string, string> = {
  noncompliant_income: "الإيراد غير المتوافق",
  interest_debt: "القروض بفائدة",
  interest_investments: "الاستثمارات بفائدة",
  liquid_assets: "الأصول السائلة",
};
export const reasonLabels: Record<string, string> = {
  KILL_SWITCH: "الإيقاف الطارئ شغّال",
  SHARIA_UNVERIFIED: "الفحص الشرعي غير مكتمل",
  SHARIA_NON_COMPLIANT: "السهم غير مستوفٍ للفحص الشرعي",
  USE_PORTFOLIO_REVIEW: "افتح تقييم المحفظة لحساب الكمية بالسياسة الحالية",
  EQUITY: "قيمة المحفظة غير متاحة",
  SETTLED_CASH_AND_RESERVATIONS: "الكاش المسوّى أو الحجز غير متاح",
  POSITION_MARKS: "أسعار أو كميات بعض المراكز غير موثقة",
  SECTOR_MAPPING: "القطاع غير معروف لبعض المراكز",
  PLANNED_OPEN_RISK: "مخاطر المراكز أو الوقف غير متاحة",
  PENDING_RISK: "مخاطر الأوامر المعلقة غير متاحة",
  DAILY_LOSS_HISTORY: "مرجع خسارة اليوم غير متاح",
  DRAWDOWN_HISTORY: "سجل قيمة المحفظة غير كافٍ لقياس التراجع",
  CURRENT_SNAPSHOT: "توقيت بيانات المحفظة يحتاج تحديث",
  COST_CONFIGURATION: "حدد العمولة والضرائب حسب حسابك",
  CANDIDATE_SECTOR_UNKNOWN: "قطاع السهم غير معروف",
  TURNOVER_UNKNOWN: "حجم التداول المرجعي غير متاح",
  MINIMUM_LIQUIDITY: "السيولة أقل من الحد",
  DAILY_LOSS_LIMIT: "وصلت لحد خسارة اليوم",
  DRAWDOWN_LIMIT: "وصلت لحد التراجع",
  PENDING_EXPOSURE_UNKNOWN: "قيمة أو قطاع الأوامر المعلقة غير معروف",
  MINIMUM_REWARD_TO_RISK: "العائد إلى المخاطرة بعد التكاليف أقل من الحد",
  OPEN_POSITIONS_LIMIT: "وصلت للحد الأقصى للمراكز",
  TRADE_RISK: "حد مخاطرة الصفقة",
  STOCK_ALLOCATION: "حد تخصيص السهم",
  SECTOR_ALLOCATION: "حد تخصيص القطاع",
  TOTAL_ALLOCATION: "حد إجمالي التعرض",
  PORTFOLIO_RISK: "حد المخاطر المجمّعة",
  BUYING_POWER: "القوة الشرائية لا تكفي",
  CURRENT_TECHNICAL_SETUP_REQUIRED: "محتاج خطة فنية من آخر جلسة مكتملة",
  ADD_TECHNICAL_CONFIRMATION_REQUIRED:
    "التعزيز محتاج اتجاه داعم وسعر داخل النطاق وفوق الوقف",
  USE_BOUNDED_ADD_SIZE: "استخدم الكمية اللي حسبها تقييم المخاطر",
  NO_ELIGIBLE_ADD_SETUP: "شروط التعزيز غير مستوفاة",
  RAISED_STOP_REQUIRED:
    "مستوى الوقف المقترح لازم يكون أعلى من الوقف الحالي وأقل من السعر",
  MARK_SETTLED_SHARES_OR_FEES_MISSING:
    "السعر أو الأسهم القابلة للبيع أو الرسوم غير متاحة",
  SELL_SIZE_OR_SETTLEMENT_LIMIT:
    "كمية البيع أكبر من المتاح للتسوية أو غير مناسبة للسيناريو",
  EXISTING_CONCENTRATION_BREACH: "المحفظة فيها تخصيص فوق الحدود الحالية",
  POSITION_STOP_BREACHED: "مركز مفتوح وصل للوقف أو كسره",
  INCONSISTENT_EQUITY: "الكاش المدخل أكبر من قيمة المحفظة",
  PASSED_ALL_CHECKS: "البيانات المراجعة تستوفي كل الاختبارات",
  NO_REVIEWED_EVIDENCE: "مفيش بيانات مراجَعة منشورة في التطبيق للسهم",
  REVIEW_OUTDATED: "انتهت صلاحية المراجعة",
  ORDINARY_SHARE_UNVERIFIED: "نوع الورقة المالية غير متحقق منه",
  OUTSIDE_METHOD_SCOPE: "الورقة خارج نطاق فحص الأسهم العادية",
  PROHIBITED_ACTIVITY: "النشاط الرئيسي غير مستوفٍ",
  ACTIVITY_UNVERIFIED: "النشاط الرئيسي غير مؤكد",
  FINANCIALS_MISSING_OR_OUTDATED: "القوائم المالية ناقصة أو قديمة",
};
export function reason(code: string) {
  if (reasonLabels[code]) return reasonLabels[code];
  const key = code.replace(/^(EXCEEDED_|MISSING_)/, "").toLowerCase();
  return ratiosAr[key]
    ? (code.startsWith("EXCEEDED") ? "تجاوز الحد · " : "بيانات ناقصة · ") +
        ratiosAr[key]
    : code;
}
export const formatRisk = (value: Numeric | undefined, percent = false) =>
  value == null
    ? "غير متاح"
    : new Intl.NumberFormat("ar-EG", {
        maximumFractionDigits: 2,
        ...(percent ? { style: "percent" } : {}),
      }).format(Number(value));

export async function ownerRequest<T>(
  endpoint: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const response = await fetch("/api/v1/" + endpoint, {
    cache: "no-store",
    credentials: "same-origin",
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (response.status === 403 || payload === null)
    throw new Error("افتح التطبيق من عنوان HTTPS الخاص بالمالك وسجّل الدخول.");
  if (response.status === 409)
    throw new Error(
      "في مراجعة محفوظة بتاريخ مطابق. استخدم تاريخ مراجعة جديد عند وجود بيانات جديدة.",
    );
  if (response.status === 422)
    throw new Error("راجع القيم والمصادر والتواريخ المطلوبة.");
  if (!response.ok)
    throw new Error("تعذّر إتمام الطلب. راجع الرمز أو مزامنة ثاندر.");
  return payload as T;
}
