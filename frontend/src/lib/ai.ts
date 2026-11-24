import type { Freshness } from "@/lib/thndr";

export interface Analysis {
  ticker: string;
  risk_blockers: string[];
  sharia_status: "COMPLIANT" | "NON_COMPLIANT" | "UNVERIFIED" | null;
  company: string;
  signal: string;
  decision: string;
  explanation_ar: string;
  provider: string | null;
  price: number | null;
  price_timestamp: string | null;
  reference_session: string | null;
  freshness: Freshness;
  market_status: string;
  technical_rating: string | null;
  score: number | null;
  agreement_pct: number | null;
  volatility_pct: number | null;
  relative_volume: number | null;
  breakout: string | null;
  risk: string;
  suggested_shares: number | null;
  levels: {
    lower: number;
    upper: number;
    stop: number;
    targets: number[];
    reward_to_risk: number[];
    support: number | null;
    resistance: number | null;
  } | null;
  supporting_ar: string[];
  opposing_ar: string[];
  missing_ar: string[];
  invalidation_ar: string[];
  expires_at: string | null;
  horizon_ar: string | null;
  company_events: {
    event_date: string;
    title_ar: string;
    source_url: string;
  }[];
  position: {
    source: string;
    shares: number | null;
    average_price: number | null;
    exposure_pct: number | null;
    unrealized_pnl: number | null;
    action: string;
    scenarios_ar: string[];
  } | null;
  ai_status: string;
  ai_explanation_ar: string | null;
  usage: {
    estimated_ceiling_usd: number;
    estimated_charge_usd: number;
    input_tokens: number;
    output_tokens: number;
  } | null;
}

export interface AIStatus {
  status: string;
  model: string;
  daily_limit_usd: number;
  monthly_limit_usd: number;
  usage: {
    daily_estimated_usd: number;
    monthly_estimated_usd: number;
    monthly_input_tokens: number;
    monthly_output_tokens: number;
  } | null;
}

export interface Opportunity {
  ticker: string;
  company: string;
  score: number;
  components: Record<string, number>;
  analysis: Analysis;
  exposure_known: boolean;
}

export const signalLabels: Record<string, string> = {
  STRONG_BUY: "شراء قوي مشروط",
  BUY: "شراء مشروط",
  HOLD: "احتفاظ",
  WAIT: "انتظار",
  SELL: "بيع مشروط",
  STRONG_SELL: "خروج مشروط",
  NO_TRADE: "لا توجد صفقة",
  DATA_NOT_CURRENT: "البيانات تحتاج تحديث",
  INSUFFICIENT_DATA: "بيانات غير كافية",
  ADD_TO_POSITION: "دراسة تعزيز",
  PARTIAL_SELL: "تخفيف جزئي",
  FULL_EXIT: "خروج مشروط",
  MOVE_STOP_LOSS: "مراجعة رفع الوقف",
  TAKE_PARTIAL_PROFIT: "دراسة جني ربح جزئي",
};

export const aiLabels: Record<string, string> = {
  CONFIGURED: "مُعد للطلبات",
  DISABLED: "التفسير متوقف من الإعدادات",
  MISSING_API_KEY: "مفتاح OpenAI غير مُعد",
  MODEL_PRICING_REQUIRED: "أسعار النموذج غير مُعدّة",
  OK: "تفسير OpenAI متاح",
  CACHED: "تفسير محفوظ لنفس البيانات",
  NOT_A_CANDIDATE: "البيانات الحالية لا تستدعي طلب تفسير",
  DETERMINISTIC_ONLY: "تحليل حسابي",
  IN_PROGRESS: "طلب مطابق قيد التنفيذ",
  RATE_LIMITED: "انتظر قبل إعادة الطلب",
  BUDGET_EXHAUSTED: "حد تكلفة OpenAI اتملأ",
  CIRCUIT_OPEN: "طلبات OpenAI متوقفة مؤقتًا بسبب خطأ في الخدمة",
  TIMEOUT: "وقت طلب OpenAI انتهى",
  UNAVAILABLE: "OpenAI غير متاح حاليًا",
  REFUSED: "النموذج لم يرجّع تفسيرًا",
  INVALID_RESPONSE: "تعذّر التحقق من رد النموذج",
  LEDGER_UNAVAILABLE: "سجل تكاليف OpenAI غير متاح",
};

export async function aiRequest<T>(
  route: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const response = await fetch("/api/v1/ai-trading/" + route, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (
    response.status === 403 ||
    (response.status === 404 &&
      !(response.headers.get("content-type") || "").includes(
        "application/json",
      ))
  ) {
    throw new Error("افتح التطبيق من عنوان HTTPS الخاص بالمالك وسجّل الدخول.");
  }
  if (response.status === 404) throw new Error("رمز السهم غير موجود.");
  if (response.status === 422)
    throw new Error("راجع قيم السعر ورأس المال والكاش وعدد الأسهم.");
  if (response.status === 429)
    throw new Error("الطلبات متقاربة. استنى شوية وحاول تاني.");
  if (!response.ok)
    throw new Error("تعذّر إتمام التحليل. لو بتستخدم ثاندر، راجع حالة الربط.");
  return response.json() as Promise<T>;
}
