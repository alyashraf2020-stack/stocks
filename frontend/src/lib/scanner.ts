import type { Analysis } from "@/lib/ai";
import type { Freshness } from "@/lib/thndr";

export const modes: Record<string, string> = {
  MARKET: "السوق بالكامل",
  WATCHLIST: "قائمة المتابعة",
  MANUAL_PORTFOLIO: "محفظة يدوية",
  THNDR_PORTFOLIO: "محفظة ثاندر",
};

export const categories: Record<string, string> = {
  BUY_REVIEW: "شراء للمراجعة", SELL_REVIEW: "بيع للمراجعة",
  ENTRY_WATCH: "متابعة قرب الدخول", ENTRY_ZONE: "تغيّر نطاق الدخول",
  BREAKOUT: "متابعة الاختراق", HOLDING_REVIEW: "مراجعة مركز",
  RISK_BLOCKED: "محجوب بقواعد المخاطر", SHARIA_BLOCKED: "محجوب بالفحص الشرعي",
  UNAVAILABLE: "بيانات غير متاحة", MONITOR: "متابعة عامة",
  RATING_CHANGE: "تغيّر التقييم الفني", STOP: "رصد مستوى الوقف",
  TARGET: "رصد مستوى هدف", PORTFOLIO_RISK: "مخاطر المحفظة",
  SHARIA_CHANGE: "تغيّر نتيجة الفحص الشرعي", MARKET_DATA: "مشكلة في بيانات السوق",
  THNDR_CONNECTION: "اتصال ثاندر", SCANNER_FAILURE: "مشكلة في الماسح",
  KILL_SWITCH: "الإيقاف الطارئ", TECHNICAL_CHANGE: "تغيّر فني",
};

export const severity: Record<string, string> = {
  INFO: "معلومة", OPPORTUNITY: "فرصة للمراجعة", WARNING: "تنبيه", CRITICAL: "حرج",
};

export const states: Record<string, string> = {
  PENDING: "في طابور الانتظار", RUNNING: "قيد التحليل", SUCCEEDED: "اكتمل",
  FAILED: "تعذّر التشغيل", CANCELLED: "أُلغي بسبب تغيّر الإعدادات",
  UNKNOWN: "حالة غير مؤكدة", PRE_MARKET: "قبل الجلسة",
  CLOSED: "خارج ساعات التداول المجدولة", OPEN: "داخل ساعات التداول المجدولة", HALTED: "إيقاف تداول",
};

export const messages: Record<string, string> = {
  THNDR_AUTHORIZATION_OR_SYNC_REQUIRED: "اتصال ثاندر أو المزامنة محتاجين مراجعة.",
  THNDR_RATE_LIMITED: "تم الوصول للحد المسموح لمحاولات التحقق من ثاندر.",
  THNDR_UNAVAILABLE: "تعذّر التحقق من صلاحية اتصال ثاندر.",
  THNDR_POSITIONS_UNVERIFIED: "بيانات مراكز ثاندر غير مؤكدة.",
  LICENSED_INTRADAY_FEED_REQUIRED: "المتابعة داخل الجلسة محتاجة مصدر أسعار مرخّص ومتاح.",
  DATA_UNAVAILABLE: "مفيش جلسات صالحة في الكاش المحلي للسهم.",
  DATA_NOT_CURRENT: "آخر جلسة مكتملة ناقصة في الكاش المحلي.",
  INSUFFICIENT_DATA: "عدد الجلسات الموثّقة أقل من المطلوب.",
  LOCAL_ANALYSIS_FAILED: "تعذّر تحليل السهم من البيانات المحلية.",
  INACTIVE_OR_UNKNOWN_SYMBOL: "السهم غير معروف أو قيده غير نشط.",
  SESSION_CHANGED: "الجلسة اتغيّرت أثناء التحليل.",
  SETTINGS_CHANGED: "الإعدادات اتغيّرت أثناء التشغيل. حدّث الصفحة وجرب تاني.",
  POLICY_CHANGED: "قواعد المخاطر اتغيّرت بعد التحليل.",
  NO_COVERED_EOD_WINDOW_OR_FEED_REQUIRED: "مفيش جلسة مكتملة ضمن تغطية التقويم أو الفترة محتاجة مصدر لحظي.",
  HISTORICAL_SCAN: "نتيجة من جولة سابقة.",
  WATCHLIST_EMPTY: "قائمة المتابعة فاضية. ضيف الرموز اللي عايز تتابعها.",
  STOP_LEVEL_OBSERVED: "السعر المرجعي لمس مستوى الوقف المدخل أو نزل تحته.",
  TARGET_1_OBSERVED: "السعر المرجعي وصل للهدف الأول.",
  TARGET_2_OBSERVED: "السعر المرجعي وصل للهدف الثاني.",
  TARGET_3_OBSERVED: "السعر المرجعي وصل للهدف الثالث.",
  SIGNAL_EXPIRED: "صلاحية الإشارة انتهت.",
};

export function scannerTime(value: number | string | null | undefined) {
  return value == null ? "غير متاح" : new Intl.DateTimeFormat("ar-EG", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Cairo",
  }).format(new Date(typeof value === "number" ? value * 1000 : value));
}

export async function scannerRequest<T>(path: string, body?: object): Promise<T> {
  const response = await fetch("/api/v1/" + path, {
    cache: "no-store", credentials: "same-origin",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    if (response.status === 403 || !data) throw new Error("افتح التطبيق من عنوان HTTPS الخاص بالمالك.");
    throw new Error(messages[String(data.detail)] ?? "تعذّر الطلب. راجع القيم وحالة الخادم.");
  }
  return data as T;
}

export interface ScannerSettings {
  enabled: boolean;
  mode: string;
  interval_seconds: number;
  watchlist: string[];
  manual: Record<string, unknown> | null;
  muted_categories: string[];
  minimum_severity: string;
  revision: number;
}

interface Calendar {
  session_status: string;
  scheduled_status: string;
  completed_session: string | null;
  version: string;
  coverage: string[];
  live_verified: boolean;
}

export interface Summary {
  mode: string; session: string; scanned: number; analyzed: number; unchanged: number;
  opportunities: number; blocked: number; unavailable: string[]; unscanned: string[];
  notice: string | null; ai_tokens: number; provider_error: string | null; duration_seconds: number;
}

export interface Health {
  enabled: boolean; mode: string; worker_online: boolean; interval_seconds: number;
  last_heartbeat: number | null; last_success: number | null; next_scheduled: number | null;
  job_status: string | null; job_error: string | null; active_alerts: number;
  market: Calendar; last_summary: Summary | null; intraday_blocker: string;
}

export interface Job {
  id: number; mode: string; status: string; session: string;
  attempts: number; queued: number; error: string | null;
}

export interface Row {
  ticker: string; category: string; reason: string | null; analysis: Analysis | null;
  rank: number | null; qualified: boolean; reviewed_at?: string;
  flags?: Record<string, boolean | string | string[] | number | null>;
  observation?: { time_basis: string; source_timestamp: string | null } | null;
  broker_observation?: { price: number | null; source_timestamp: string | null; freshness: Freshness } | null;
}

export interface Results {
  job_id: number | null; summary: Summary | null; rows: Row[]; total: number; sectors: string[]; error?: string;
}

export interface Alert {
  id: string; category: string; severity: string; ticker?: string; created: number;
  source_timestamp: string | null; freshness: Freshness; reason: string; limitations: string[];
  read_at: number | null; acknowledged_at: number | null; requires_recheck: boolean;
}
