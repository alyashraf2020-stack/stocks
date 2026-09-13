"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  TrendingUp,
  ArrowRight,
  ShieldCheck,
  Clock,
  CheckCircle2,
  Building2,
  Calendar,
  Layers,
  Database,
  RefreshCw
} from "lucide-react";
import { getStockDetail, getStockChart, refreshStockData } from "@/lib/api";
import { Stock, ChartData } from "@/lib/types";
import InteractiveCandleChart from "@/components/InteractiveCandleChart";

export default function StockDetailPage() {
  const params = useParams();
  const ticker = (params.ticker as string)?.toUpperCase();

  const [stock, setStock] = useState<Stock | null>(null);
  const [chartData, setChartData] = useState<ChartData | null>(null);
  const [range, setRange] = useState("3M");
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRefresh = async () => {
    if (!ticker || refreshing) return;
    setRefreshing(true);
    try {
      const [updatedStock, updatedChart] = await Promise.all([
        refreshStockData(ticker),
        getStockChart(ticker, range)
      ]);
      setStock(updatedStock);
      setChartData(updatedChart);
    } catch (err: any) {
      console.error("Failed to refresh stock data:", err);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);

    getStockDetail(ticker)
      .then((s) => {
        setStock(s);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "تعذر جلب بيانات السهم");
        setLoading(false);
      });
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    setChartLoading(true);
    getStockChart(ticker, range)
      .then((c) => {
        setChartData(c);
        setChartLoading(false);
      })
      .catch(() => setChartLoading(false));
  }, [ticker, range]);

  if (loading) {
    return <div className="p-12 text-center text-sm text-gray-400">جاري تحميل تفاصيل السهم...</div>;
  }

  if (error || !stock) {
    return (
      <div className="p-12 text-center space-y-4">
        <div className="text-rose-400 font-bold">{error || "السهم غير موجود"}</div>
        <Link href="/stocks" className="text-xs text-primary font-bold hover:underline">
          العودة لدليل الأسهم
        </Link>
      </div>
    );
  }

  const isCurrent = chartData?.sessions_behind === 0;

  return (
    <div className="space-y-6">
      {/* Back link & Header */}
      <div className="space-y-2">
        <Link href="/stocks" className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors">
          <ArrowRight className="w-3.5 h-3.5" />
          <span>العودة لكل أسهم البورصة</span>
        </Link>

        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surfaceBorder pb-6">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="text-3xl font-black text-white font-mono">{stock.ticker}</span>
              <span className="text-xl font-bold text-gray-300">{stock.arabic_name}</span>
            </div>
            <div className="text-xs text-gray-400 flex flex-wrap items-center gap-3">
              <span>{stock.english_name}</span>
              {stock.isin && (
                <>
                  <span>•</span>
                  <span>ISIN: <span className="font-mono text-gray-300 num-ltr">{stock.isin}</span></span>
                </>
              )}
              <span>•</span>
              <span className="bg-surfaceHover border border-surfaceBorder px-2 py-0.5 rounded text-[11px] text-gray-300">
                {stock.sector}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Unified Refresh Synchronization Action */}
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 bg-surfaceHover hover:bg-surfaceBorder text-gray-200 hover:text-white font-bold px-4 py-2.5 rounded-xl border border-surfaceBorder transition-all disabled:opacity-50 text-sm cursor-pointer shadow-sm"
              title="مزامنة بيانات السهم والرسم البياني مع البورصة"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin text-primary" : "text-gray-400"}`} />
              <span>{refreshing ? "جاري التحديث..." : "تحديث البيانات"}</span>
            </button>

            {/* Direct Live Analysis CTA */}
            <Link
              href={`/live-analysis?ticker=${stock.ticker}`}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-background font-black px-5 py-2.5 rounded-xl transition-all shadow-lg hover:shadow-primary/20 text-sm"
            >
              <TrendingUp className="w-4 h-4" />
              <span>تحليل السعر اللحظي لهذا السهم</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Snapshot Stats Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-surface border border-surfaceBorder rounded-xl p-4">
          <span className="text-xs text-gray-400 block mb-1">آخر إغلاق مسجل</span>
          <span className="text-xl font-black text-white font-mono num-ltr">
            {stock.latest_close ? `${stock.latest_close.toFixed(2)} ج.م` : "—"}
          </span>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-xl p-4">
          <span className="text-xs text-gray-400 block mb-1">آخر جلسة EOD</span>
          <span className="text-sm font-bold text-white font-mono num-ltr">
            {stock.latest_session_date || chartData?.latest_available_session || "—"}
          </span>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-xl p-4">
          <span className="text-xs text-gray-400 block mb-1">حالة حداثة البيانات</span>
          <div className="flex items-center gap-1.5 mt-0.5">
            {isCurrent ? (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-400">
                <CheckCircle2 className="w-4 h-4" />
                <span>محدث</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-400">
                <Clock className="w-4 h-4" />
                <span>غير محدث ({stock.sessions_behind ?? chartData?.sessions_behind ?? 1} جلسة تأخير)</span>
              </span>
            )}
          </div>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-xl p-4">
          <span className="text-xs text-gray-400 block mb-1">مصدر البيانات الأصلي</span>
          <span className="text-xs font-medium text-gray-300 block truncate">
            {stock.actual_provider || chartData?.actual_provider || chartData?.bars[0]?.actual_provider || "—"}
          </span>
        </div>
      </div>

      {/* Interactive Candlestick Chart */}
      {chartData && chartData.bars.length > 0 ? (
        <InteractiveCandleChart
          bars={chartData.bars}
          selectedRange={range}
          onRangeChange={setRange}
          loading={chartLoading}
        />
      ) : (
        <div className="bg-surface border border-surfaceBorder rounded-2xl p-12 text-center text-gray-400 text-sm">
          البيانات التاريخية غير متاحة حالياً لهذا السهم من المزودين المعتمدين.
        </div>
      )}

      {/* Technical Metadata & Provenance Footer */}
      <div className="bg-surface border border-surfaceBorder rounded-xl p-4 text-xs text-gray-400 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-primary" />
          <span>مرجع سجل الأصول: {stock.source}</span>
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-500" />
          <span>آخر تحديث لقيد السهم: <span className="font-mono text-gray-300 num-ltr">{stock.source_updated_at}</span></span>
        </div>
      </div>
    </div>
  );
}