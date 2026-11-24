export type Freshness =
  | "REALTIME_VERIFIED"
  | "DELAYED"
  | "HISTORICAL"
  | "MANUAL"
  | "STALE"
  | "UNKNOWN";
export const freshnessLabel: Record<Freshness, string> = {
  REALTIME_VERIFIED: "لحظي موثّق",
  DELAYED: "متأخر",
  HISTORICAL: "تاريخي",
  MANUAL: "يدوي",
  STALE: "قديم",
  UNKNOWN: "غير مؤكد",
};
export const toolLabels: Record<string, string> = {
  check_eligibility: "حالة الحساب وأهلية التداول",
  get_portfolio_overview: "ملخص الحساب والمراكز",
  get_account_activities: "حركة الحساب",
  get_orders: "الأوامر المفتوحة",
  get_watchlist: "قائمة المتابعة",
  get_market_status: "حالة السوق",
  get_assets_info: "بيانات الأسهم وأسعارها",
  get_trading_stats: "أداء التداول",
};
export const stateLabels: Record<string, string> = {
  NOT_CONFIGURED: "محتاج إعداد على السيرفر",
  DISCONNECTED: "غير متصل",
  AUTHORIZING: "في انتظار موافقتك",
  CONNECTED: "متصل للقراءة",
  RECONNECT_REQUIRED: "محتاج إعادة ربط",
  REVOCATION_PENDING: "إلغاء الوصول قيد المحاولة",
};
export interface Connection {
  status: string;
  permissions: string[];
  available: string[];
  unavailable: string[];
  last_sync: string | null;
  error: string | null;
  freshness: Freshness;
}
interface Quote {
  price: number;
  validation_status: string;
  freshness: Freshness;
  source_timestamp: string | null;
}
type Num = number | null;
export interface Portfolio {
  account: {
    registration_status: string | null;
    eligible_for_egx: boolean | null;
  } | null;
  total_value: Num;
  available_cash: Num;
  invested_amount: Num;
  realized_pnl: Num;
  unrealized_pnl: Num;
  last_sync: string | null;
  market_status: string;
  issues: Record<string, string>;
  holdings:
    | {
        ticker: string;
        instrument_id: string | null;
        quantity: Num;
        average_price: Num;
        market_value: Num;
        unrealized_pnl: Num;
        quote: Quote | null;
      }[]
    | null;
}
const messages: Record<string, string> = {
  OWNER_GATEWAY_REQUIRED:
    "افتح التطبيق من عنوان HTTPS الخاص بصاحب الحساب وسجّل الدخول.",
  NOT_CONFIGURED: "إعدادات ربط ثاندر على السيرفر لسه ناقصة.",
  REGISTRATION_REFUSED:
    "ثاندر رفض تسجيل التطبيق بعنوان الرجوع الحالي. راجع الدليل الرسمي.",
  REGISTRATION_UNAVAILABLE: "ثاندر لم يُتح تسجيل التطبيق تلقائيًا.",
  INVALID_REGISTRATION: "تعذّر تأكيد تسجيل التطبيق عند ثاندر.",
  INVALID_METADATA: "تعذّر التحقق من إعدادات ثاندر الرسمية.",
  NETWORK_UNAVAILABLE: "الاتصال بثاندر مش متاح حاليًا.",
  MCP_UNAVAILABLE: "تعذّر الوصول لخدمة ثاندر. جرّب المزامنة مرة تانية.",
  RATE_LIMITED: "في طلبات متقاربة. استنى شوية قبل المحاولة التالية.",
  BUSY: "في عملية شغالة. جرّب بعد ثوانٍ.",
  INVALID_OAUTH_STATE: "جلسة الربط غير صالحة أو انتهت. ابدأ الربط من جديد.",
  INVALID_CALLBACK: "تعذّر التحقق من رد تسجيل الدخول.",
  CONSENT_DECLINED: "موافقة الربط لم تكتمل.",
  RECONNECT_REQUIRED: "صلاحية الاتصال انتهت. افصل الحساب واربطه من جديد.",
  MISSING_PERMISSION: "الصلاحية المطلوبة مش متاحة.",
  NO_USABLE_READS: "الصلاحيات أو البيانات المتاحة لا تكفي لعرض ملخص الحساب.",
  PERMISSIONS_CHANGED:
    "صلاحيات الحساب اتغيّرت. اعمل مزامنة لعرض البيانات المسموح بها.",
  STORAGE_UNREADABLE:
    "تعذّر فتح التخزين المشفّر. راجع مفتاح التشفير على السيرفر.",
  UNEXPECTED_GRANT:
    "ثاندر أعاد صلاحيات مختلفة عن القراءة. افصل الاتصال لإلغائها.",
  UNSUPPORTED_TOOL_SCHEMA: "صيغة أداة ثاندر الحالية تحتاج مراجعة.",
  INVALID_BROKER_RESPONSE: "تعذّر التحقق من بيانات ثاندر.",
  TOOL_UNAVAILABLE: "الأداة غير متاحة حاليًا.",
  DISCONNECT_FIRST: "افصل الربط الحالي الأول.",
};
export const errorMessage = (code: string) =>
  messages[code] || "تعذّر إتمام الطلب. راجع حالة الربط وحاول مجددًا.";
export const dateLabel = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("ar-EG", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Africa/Cairo",
      }).format(new Date(value))
    : "لم تتم مزامنة";
export const numberLabel = (value: Num) =>
  value === null
    ? "غير متاح"
    : new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 4 }).format(
        value,
      );
export async function thndr<T>(
  path: string,
  method = "GET",
  signal?: AbortSignal,
): Promise<T> {
  // This host must be the owner's gateway. Never send brokerage credentials from JS.
  const response = await fetch("/api/v1/integrations/thndr/" + path, {
    method,
    signal,
    cache: "no-store",
    credentials: "same-origin",
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body === null)
    throw new Error(
      errorMessage(
        body?.detail ??
          (response.status === 404 ? "OWNER_GATEWAY_REQUIRED" : ""),
      ),
    );
  return body as T;
}
