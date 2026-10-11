"use client";

import React, { useState, useEffect, useRef } from "react";
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
import { getStockDetail, getStockChart, refreshStockData, getStockTechnical } from "@/lib/api";
import { Stock, ChartData, StockPlan } from "@/lib/types";
import InteractiveCandleChart from "@/components/InteractiveCandleChart";
import CompanyProfileCard from "@/components/CompanyProfileCard";
import TechnicalSummaryCard from "@/components/TechnicalSummaryCard";

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
  const [companyRefreshKey, setCompanyRefreshKey] = useState(0);
  const [report, setReport] = useState<StockPlan | null>(null);
  const [reportLoading, setReportLoading] = useState(true);
  const [reportError, setReportError] = useState<string | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const refreshController = useRef<AbortController | null>(null);

  const handleRefresh = async () => {
    if (!ticker || refreshing) return;
    const controller = new AbortController();
    refreshController.current = controller;
    setRefreshing(true);
    setReportLoading(true);
    setReportError(null);
    try {
      const updatedStock = await refreshStockData(ticker, controller.signal);
      if (controller.signal.aborted) return;
      setStock(updatedStock);
      const results = await Promise.allSettled([getStockChart(ticker, range, controller.signal), getStockTechnical(ticker, controller.signal)]);
      if (controller.signal.aborted) return;
      if (results[0].status === "fulfilled") { setChartData(results[0].value); setChartError(null); }
      else { setChartData(null); setChartError(results[0].reason.message); }
      if (results[1].status === "fulfilled") setReport(results[1].value);
      else { setReport(null); setReportError(results[1].reason.message); }
    } catch (err: any) {
      if (controller.signal.aborted) return;
      setReport(null);
      setReportError(err.message || "تعذر تحديث البيانات");
    } finally {
      if (!controller.signal.aborted) {
        setCompanyRefreshKey((value) => value + 1);
        setRefreshing(false);
        setReportLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setRefreshing(false);
    setError(null);
    setStock(null);
    setReport(null);
    setReportLoading(true);
    setReportError(null);
    const controller = new AbortController();
    getStockDetail(ticker, controller.signal)
      .then((s) => {
        if (controller.signal.aborted) return;
        setStock(s);
        setLoading(false);
        return getStockTechnical(ticker, controller.signal)
          .then(data => { if (!controller.signal.aborted) setReport(data); })
          .catch(err => { if (!controller.signal.aborted) setReportError(err.message); })
          .finally(() => { if (!controller.signal.aborted) setReportLoading(false); });
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err.message || "تعذر جلب بيانات السهم");
        setLoading(false);
      });
    return () => { controller.abort(); refreshController.current?.abort(); };
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    setChartLoading(true);
    setChartData(null);
    setChartError(null);
    const controller = new AbortController();
    getStockChart(ticker, range, controller.signal)
      .then((c) => {
        if (controller.signal.aborted) return;
        setChartData(c);
        setChartLoading(false);
      })
      .catch(err => { if (!controller.signal.aborted) { setChartError(err.message); setChartLoading(false); } });
    return () => controller.abort();
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
            {(report?.latest_close ?? chartData?.latest_close ?? stock.latest_close)?.toFixed(2) ?? "—"} ج.م
          </span>
          {report?.technical_rating && <p className={`text-xs font-mono mt-1 ${report.technical_rating.daily_change >= 0 ? "text-emerald-400" : "text-rose-400"}`} dir="ltr">{report.technical_rating.daily_change >= 0 ? "+" : ""}{report.technical_rating.daily_change.toFixed(2)} ({report.technical_rating.daily_change_pct.toFixed(2)}%)</p>}
          {report?.technical_rating && <p className="text-[10px] text-gray-500 mt-1">عن إغلاق {report.technical_rating.daily_reference_session}</p>}
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-xl p-4">
          <span className="text-xs text-gray-400 block mb-1">آخر جلسة EOD</span>
          <span className="text-sm font-bold text-white font-mono num-ltr">
            {report?.latest_available_session || chartData?.latest_available_session || stock.latest_session_date || "—"}
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
                <span>{(chartData?.sessions_behind ?? stock.sessions_behind) == null ? "لا توجد بيانات كافية" : `غير محدث (${chartData?.sessions_behind ?? stock.sessions_behind} جلسة تأخير)`}</span>
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
          loading={chartLoading || refreshing}
          rangeInfo={chartData}
          tradePlan={report?.latest_available_session === chartData.latest_available_session && report?.sessions_behind === 0 ? report.trade_plan : null}
        />
      ) : (
        <div className="bg-surface border border-surfaceBorder rounded-2xl p-12 text-center text-gray-400 text-sm">
          {chartLoading ? "جاري تحميل الشارت..." : chartError || "البيانات التاريخية غير متاحة حالياً لهذا السهم من المزودين المعتمدين."}
        </div>
      )}

      <TechnicalSummaryCard report={report} loading={reportLoading} error={reportError} />

      {/* Technical Metadata & Provenance Footer */}
      {["MBSC", "MPCI", "BIOC"].includes(stock.ticker) && <CompanyProfileCard ticker={stock.ticker}
        refreshKey={companyRefreshKey} latestBar={chartData?.bars[chartData.bars.length - 1]} />}

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
