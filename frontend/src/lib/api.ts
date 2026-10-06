import { StockListResponse, Stock, ChartData, LiveAnalysisResult, MarketStatus, CompanyProfile, StockPlan, StockPlansResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

export async function getAllStockPlans(signal?: AbortSignal): Promise<StockPlansResponse> {
  const res = await fetch(`${API_BASE}/egx/plans`, { cache: "no-store", signal });
  if (!res.ok) throw new Error("تعذر تحميل خطط الأسهم. تأكد من تشغيل الباك إند وأعد المحاولة.");
  return res.json();
}

export async function refreshStockPlan(ticker: string, signal?: AbortSignal): Promise<StockPlan> {
  const res = await fetch(`${API_BASE}/egx/plans/${encodeURIComponent(ticker)}/refresh`, {
    method: "POST", cache: "no-store", signal,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `تعذر تحديث خطة ${ticker}`);
  }
  return res.json();
}

export async function getMarketStatus(): Promise<MarketStatus> {
  const res = await fetch(`${API_BASE}/egx/market/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("تعذر جلب حالة السوق");
  return res.json();
}

export async function getStocks(params?: {
  q?: string;
  sector?: string;
  status?: string;
  index_name?: string;
}): Promise<StockListResponse> {
  const query = new URLSearchParams();
  if (params?.q) query.set("q", params.q);
  if (params?.sector) query.set("sector", params.sector);
  if (params?.status) query.set("status", params.status);
  if (params?.index_name) query.set("index_name", params.index_name);

  const res = await fetch(`${API_BASE}/egx/stocks?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("تعذر جلب قائمة الأسهم");
  return res.json();
}

export async function getSectors(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/egx/stocks/sectors`, { cache: "no-store" });
  if (!res.ok) throw new Error("تعذر جلب القطاعات");
  return res.json();
}

export async function getStockDetail(ticker: string): Promise<Stock> {
  const res = await fetch(`${API_BASE}/egx/stocks/${ticker}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`تعذر جلب بيانات السهم ${ticker}`);
  return res.json();
}

export async function getStockCompany(ticker: string): Promise<CompanyProfile> {
  const res = await fetch(`${API_BASE}/egx/stocks/${ticker}/company`, { cache: "no-store" });
  if (!res.ok) throw new Error(`تعذر جلب ملف الشركة ${ticker}`);
  return res.json();
}

export async function refreshStockData(ticker: string): Promise<Stock> {
  const res = await fetch(`${API_BASE}/egx/stocks/${ticker}/refresh`, {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`تعذر تحديث بيانات السهم ${ticker}`);
  return res.json();
}

export async function getStockChart(ticker: string, range: string = "3M"): Promise<ChartData> {
  const res = await fetch(`${API_BASE}/egx/stocks/${ticker}/chart?range=${range}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`تعذر جلب الرسم البياني للسهم ${ticker}`);
  return res.json();
}

export async function submitManualEod(data: {
  ticker: string;
  session_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}): Promise<{
  status: string;
  ticker: string;
  session_date: string;
  actual_provider: string;
  message_ar: string;
}> {
  const res = await fetch(`${API_BASE}/egx/live-analysis/manual-eod`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "تعذر حفظ بيانات الجلسة المكتملة");
  }
  return res.json();
}

export async function postLiveAnalysis(data: {
  ticker: string;
  current_price: number;
  capital: number;
  owns_stock?: boolean;
  buy_price?: number;
  shares_owned?: number;
  bid_depth_qty?: number;
  ask_depth_qty?: number;
}): Promise<LiveAnalysisResult> {
  const res = await fetch(`${API_BASE}/egx/live-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "تعذر إجراء التحليل اللحظي للسهم");
  }
  return res.json();
}
