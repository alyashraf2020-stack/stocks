import { StockListResponse, Stock, ChartData, LiveAnalysisResult, MarketStatus } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

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

export async function postLiveAnalysis(data: {
  ticker: string;
  current_price: number;
  capital: number;
  owns_stock?: boolean;
  buy_price?: number;
  shares_owned?: number;
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