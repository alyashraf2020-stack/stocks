"use client";

import React, { useState, useEffect, Suspense, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  TrendingUp,
  Coins,
  Wallet,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ArrowDownCircle
} from "lucide-react";
import { postLiveAnalysis, getStockDetail } from "@/lib/api";
import { Stock, LiveAnalysisResult, TradePlan } from "@/lib/types";
import StockSearchInput from "@/components/StockSearchInput";
import DecisionCard from "@/components/DecisionCard";

function parseTicker(param: string | null): string | null {
  if (!param) return null;
  let cleaned = param.trim();
  // Strip any concatenated URL or domain artifact, e.g. "KORAlocalhost:3000/live-analysis"
  for (const artifact of ["localhost", "http:", "https:", "/", "?", "&", ":", "3000"]) {
    if (cleaned.includes(artifact)) {
      cleaned = cleaned.split(artifact)[0];
    }
  }
  cleaned = cleaned.trim().toUpperCase();
  // Validate that it looks like a valid EGX equity ticker (alphanumeric, 2-10 chars)
  if (/^[A-Z0-9]{2,10}$/.test(cleaned)) {
    return cleaned;
  }
  return null;
}

function LiveAnalysisContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTicker = searchParams.get("ticker");
  const urlTicker = parseTicker(rawTicker);

  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [loadingStock, setLoadingStock] = useState<boolean>(false);
  const [currentPrice, setCurrentPrice] = useState<string>("");
  const [capital, setCapital] = useState<string>("100000");

  // Optional existing position state
  const [ownsStock, setOwnsStock] = useState<boolean>(false);
  const [buyPrice, setBuyPrice] = useState<string>("");
  const [sharesOwned, setSharesOwned] = useState<string>("");

  // Analysis result state
  const [result, setResult] = useState<LiveAnalysisResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Stale-response protection ref: tracks current target ticker
  const activeTickerRef = useRef<string | null>(urlTicker);

  // Session refresh & previous plan state
  const [lastCheckTime, setLastCheckTime] = useState<string | null>(null);
  const [newSessionDetected, setNewSessionDetected] = useState<boolean>(false);
  const [newSessionNotice, setNewSessionNotice] = useState<string | null>(null);
  const [previousPlan, setPreviousPlan] = useState<TradePlan | null>(null);

  // Synchronized refs to read latest values in callbacks without stale closures
  const selectedStockRef = useRef<Stock | null>(selectedStock);
  selectedStockRef.current = selectedStock;
  const resultRef = useRef<LiveAnalysisResult | null>(result);
  resultRef.current = result;

  // Reset analysis results and user inputs when changing or clearing stock
  const resetAnalysisResult = React.useCallback(() => {
    setResult(null);
    setError(null);
    setCurrentPrice("");
    setBuyPrice("");
    setSharesOwned("");
    setNewSessionDetected(false);
    setNewSessionNotice(null);
    setPreviousPlan(null);
  }, []);

  // Check freshness and detect completed sessions
  const checkFreshness = React.useCallback(async (isImmediate: boolean = false) => {
    const currentStock = selectedStockRef.current;
    const currentTicker = activeTickerRef.current;
    if (!currentStock || !currentTicker) return;

    // Record check time (HH:MM)
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setLastCheckTime(timeStr);

    try {
      const updated = await getStockDetail(currentTicker);

      // Stale response guard
      if (activeTickerRef.current !== currentTicker) return;

      const oldSession = currentStock.latest_session_date;
      const newSession = updated.latest_session_date;
      const oldCount = currentStock.analytical_bars_count || 0;
      const newCount = updated.analytical_bars_count || 0;

      const isNewSession = Boolean(
        oldSession &&
        newSession &&
        (newSession !== oldSession || newCount > oldCount)
      );

      if (isNewSession) {
        // A new completed session is detected:
        // 1. Preserve previous plan for historical context
        if (resultRef.current?.trade_plan) {
          setPreviousPlan(resultRef.current.trade_plan);
        }
        // 2. Invalidate old live decision
        setResult(null);
        // 3. Mark new session detected and show notice banner
        setNewSessionDetected(true);
        setNewSessionNotice(
          'تم تحديث بيانات السهم بعد جلسة جديدة. اضغط "تحليل الآن" لإعادة تقييم السعر الحالي بالخطة الجديدة.'
        );
        // 4. Update stock data (user inputs: capital, ownsStock, buyPrice, sharesOwned, currentPrice are preserved)
        setSelectedStock(updated);
      } else {
        // latest_analytical_session is unchanged:
        // do nothing (preserve all inputs, trade plan, and decision).
        setSelectedStock((prev) => (prev ? { ...prev, ...updated } : updated));
      }
    } catch {
      // Silently ignore background polling errors
    }
  }, []);

  // Canonical stock selection handler
  const handleStockSelect = React.useCallback((stock: Stock) => {
    const targetTicker = stock.ticker.trim().toUpperCase();
    activeTickerRef.current = targetTicker;

    // Immediately set selected stock and reset previous analysis results
    setSelectedStock(stock);
    resetAnalysisResult();

    // Synchronize URL query parameter without full reload
    router.replace(`/live-analysis?ticker=${encodeURIComponent(targetTicker)}`);

    // Fetch full stock details asynchronously with stale-response protection
    setLoadingStock(true);
    getStockDetail(targetTicker)
      .then((detail) => {
        if (activeTickerRef.current === targetTicker) {
          setSelectedStock(detail);
        }
      })
      .catch((err: any) => {
        if (activeTickerRef.current === targetTicker) {
          setError(err.message || "تعذر تحميل بيانات السهم المحدد");
        }
      })
      .finally(() => {
        if (activeTickerRef.current === targetTicker) {
          setLoadingStock(false);
        }
      });
  }, [router, resetAnalysisResult]);

  // Synchronize when URL ticker changes externally (e.g. browser back/forward or direct link change)
  useEffect(() => {
    if (!urlTicker) {
      if (selectedStock && !activeTickerRef.current) {
        setSelectedStock(null);
        resetAnalysisResult();
      }
      return;
    }

    const normalizedUrlTicker = urlTicker.trim().toUpperCase();

    // Already active or matching current stock
    if (selectedStock && selectedStock.ticker.toUpperCase() === normalizedUrlTicker) {
      return;
    }
    if (activeTickerRef.current && activeTickerRef.current.toUpperCase() === normalizedUrlTicker) {
      return;
    }

    activeTickerRef.current = normalizedUrlTicker;
    resetAnalysisResult();
    setLoadingStock(true);
    getStockDetail(normalizedUrlTicker)
      .then((detail) => {
        if (activeTickerRef.current === normalizedUrlTicker) {
          setSelectedStock(detail);
        }
      })
      .catch((err: any) => {
        if (activeTickerRef.current === normalizedUrlTicker) {
          setError(err.message || "تعذر تحميل بيانات السهم المحدد");
        }
      })
      .finally(() => {
        if (activeTickerRef.current === normalizedUrlTicker) {
          setLoadingStock(false);
        }
      });
  }, [urlTicker, selectedStock, resetAnalysisResult]);

  // Auto-refresh effect: 5-minute background timer + focus and visibility listeners
  useEffect(() => {
    if (!selectedStock?.ticker) return;

    const now = new Date();
    setLastCheckTime(now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));

    // 1. Background check every 5 minutes
    const intervalId = setInterval(() => {
      checkFreshness(false);
    }, 5 * 60 * 1000);

    // 2. Immediate check on tab visibility change
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkFreshness(true);
      }
    };

    // 3. Immediate check on window focus
    const handleFocus = () => {
      checkFreshness(true);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleFocus);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
    };
  }, [selectedStock?.ticker, checkFreshness]);

  const isPriceValid = !isNaN(parseFloat(currentPrice)) && parseFloat(currentPrice) > 0;
  const canAnalyze = Boolean(selectedStock && isPriceValid && !loading);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStock) {
      setError("يرجى اختيار سهم من البورصة المصرية أولاً");
      return;
    }

    const priceNum = parseFloat(currentPrice);
    const capitalNum = parseFloat(capital);

    if (isNaN(priceNum) || priceNum <= 0) {
      setError("يرجى إدخال سعر لحظي صحيح أكبر من الصفر");
      return;
    }

    if (isNaN(capitalNum) || capitalNum <= 0) {
      setError("يرجى إدخال رأس مال صحيح أكبر من الصفر");
      return;
    }

    const targetTicker = selectedStock.ticker;
    setLoading(true);
    setError(null);

    try {
      const res = await postLiveAnalysis({
        ticker: targetTicker,
        current_price: priceNum,
        capital: capitalNum,
        owns_stock: ownsStock,
        buy_price: ownsStock && buyPrice ? parseFloat(buyPrice) : undefined,
        shares_owned: ownsStock && sharesOwned ? parseInt(sharesOwned, 10) : undefined,
      });
      if (activeTickerRef.current === targetTicker) {
        setResult(res);
        if (res.previous_plan) {
          setPreviousPlan(res.previous_plan);
        }
        setNewSessionNotice(null);
        setNewSessionDetected(false);
      }
    } catch (err: any) {
      if (activeTickerRef.current === targetTicker) {
        setError(err.message || "حدث خطأ أثناء تحليل السعر اللحظي");
      }
    } finally {
      if (activeTickerRef.current === targetTicker) {
        setLoading(false);
      }
    }
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Page Title */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-bold text-primary">
          <TrendingUp className="w-3.5 h-3.5" />
          <span>الميزة الجوهرية للمنصة</span>
        </div>
        <h1 className="text-2xl sm:text-4xl font-black text-white">
          تحليل السعر اللحظي المباشر وقرار التداول
        </h1>
        <p className="text-xs sm:text-sm text-gray-400 max-w-xl mx-auto leading-relaxed">
          أدخل السعر الحالي للسهم من شاشة تداولك أو تطبيق الوسيط لمقارنته فورياً مع التحليل الفني لآخر جلسة والحصول على قرار تداول شرائي آمن.
        </p>
      </div>

      {/* Input Workbench Form */}
      <form
        onSubmit={handleAnalyze}
        className="bg-surface border border-surfaceBorder rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Stock Selector */}
          <div className="space-y-2 sm:col-span-2">
            <label className="text-xs font-bold text-gray-300 block">
              1. اختر السهم المصري <span className="text-rose-400">*</span>
            </label>
            <StockSearchInput
              selectedTicker={selectedStock?.ticker || urlTicker || undefined}
              selectedStock={selectedStock}
              onSelect={handleStockSelect}
              placeholder="ابحث بالرمز أو اسم الشركة المصرية..."
            />
            {loadingStock && (
              <div className="text-xs text-gray-400 pt-1">جاري تحميل بيانات السهم ومطابقة الجلسات...</div>
            )}
            {selectedStock && !loadingStock && (
              <div className="space-y-1.5 pt-1">
                <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
                  <span>القطاع: <strong className="text-gray-300">{selectedStock.sector}</strong></span>
                  <span>•</span>
                  <span>حالة البيانات: <strong className={`font-bold ${selectedStock.sessions_behind === 0 ? "text-emerald-400" : "text-amber-400"}`}>{selectedStock.freshness || "غير متاح"}</strong></span>
                  <span>•</span>
                  <span>المزود: <strong className="text-gray-300">{selectedStock.actual_provider || "—"}</strong></span>
                  <span>•</span>
                  <span>آخر جلسة: <strong className="font-mono text-gray-300 num-ltr">{selectedStock.latest_session_date || "—"}</strong></span>
                  {selectedStock.analytical_bars_count !== undefined && selectedStock.analytical_bars_count !== null && (
                    <>
                      <span>•</span>
                      <span>عدد الجلسات التحليلية: <strong className="font-mono text-gray-300 num-ltr">{selectedStock.analytical_bars_count}</strong></span>
                    </>
                  )}
                </div>

                {/* Unobtrusive Auto-Refresh Status Badges */}
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
                  <span className="inline-flex items-center gap-1.5 text-emerald-400 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    التحديث التلقائي: مفعّل
                  </span>
                  {lastCheckTime && (
                    <>
                      <span>•</span>
                      <span>آخر فحص: <span className="font-mono text-gray-300 num-ltr">{lastCheckTime}</span></span>
                    </>
                  )}
                  {newSessionDetected && (
                    <>
                      <span>•</span>
                      <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30 font-bold">
                        تم تحميل جلسة جديدة
                      </span>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Current Live Price */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-300 block flex items-center justify-between">
              <span>2. السعر اللحظي الحالي (ج.م) <span className="text-rose-400">*</span></span>
              <span className="text-[11px] text-gray-500">من تطبيق الوسيط (Thndr, مباشر، إلخ)</span>
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={currentPrice}
                onChange={(e) => setCurrentPrice(e.target.value)}
                placeholder="أدخل السعر اللحظي الحالي..."
                required
                className="w-full bg-surfaceHover border border-surfaceBorder rounded-xl px-4 py-3 pl-12 text-sm text-white font-mono font-bold focus:outline-none focus:border-primary"
              />
              <span className="absolute left-3 top-3.5 text-xs text-gray-400 font-mono">ج.م</span>
            </div>

            {/* Helper Text */}
            <p className="text-xs text-primary font-medium">
              أدخل السعر الحالي من تطبيق التداول الخاص بك.
            </p>

            {/* Show latest historical close separately */}
            {selectedStock && selectedStock.latest_close && (
              <div className="bg-surfaceHover/50 border border-surfaceBorder rounded-xl p-3 text-xs text-gray-300 flex flex-wrap items-center justify-between gap-2">
                <span>
                  آخر إغلاق مسجل:{" "}
                  <strong className="font-mono text-white num-ltr">
                    {selectedStock.latest_close.toFixed(2)} ج.م
                  </strong>
                </span>
                <span>
                  جلسة:{" "}
                  <strong className="font-mono text-gray-400 num-ltr">
                    {selectedStock.latest_session_date || "—"}
                  </strong>
                </span>
              </div>
            )}
          </div>

          {/* Portfolio Capital */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-300 block flex items-center justify-between">
              <span>3. رأس المال المتاح بالمحفظة (ج.م) <span className="text-rose-400">*</span></span>
              <span className="text-[11px] text-gray-500">لحساب حجم الصفقة الآمن</span>
            </label>
            <div className="relative">
              <input
                type="number"
                step="1000"
                min="1000"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                placeholder="مثال: 100000"
                required
                className="w-full bg-surfaceHover border border-surfaceBorder rounded-xl px-4 py-3 pl-12 text-sm text-white font-mono font-bold focus:outline-none focus:border-primary"
              />
              <span className="absolute left-3 top-3.5 text-xs text-gray-400 font-mono">ج.م</span>
            </div>
          </div>
        </div>

        {/* Existing Position Toggle */}
        <div className="border-t border-surfaceBorder pt-4 space-y-4">
          <label className="flex items-center gap-3 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={ownsStock}
              onChange={(e) => setOwnsStock(e.target.checked)}
              className="w-4 h-4 rounded border-surfaceBorder bg-surfaceHover text-primary focus:ring-primary"
            />
            <span className="text-sm font-bold text-gray-300">
              أنا أملك هذا السهم بالفعل في محفظتي (تقييم مركز قائم)
            </span>
          </label>

          {ownsStock && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-surfaceHover/60 border border-surfaceBorder rounded-xl p-4">
              <div className="space-y-1">
                <label className="text-xs text-gray-400">متوسط سعر الشراء (ج.م)</label>
                <input
                  type="number"
                  step="0.01"
                  value={buyPrice}
                  onChange={(e) => setBuyPrice(e.target.value)}
                  placeholder="مثال: 135.00"
                  className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">عدد الأسهم المملوكة</label>
                <input
                  type="number"
                  step="1"
                  value={sharesOwned}
                  onChange={(e) => setSharesOwned(e.target.value)}
                  placeholder="مثال: 500"
                  className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono"
                />
              </div>
            </div>
          )}
        </div>

        {/* New Session Notice Banner */}
        {newSessionNotice && (
          <div className="bg-primary/10 border border-primary/30 rounded-xl p-4 text-xs text-primary flex items-start justify-between gap-3 animate-fadeIn">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-primary flex-shrink-0" />
              <span className="font-bold leading-relaxed">{newSessionNotice}</span>
            </div>
            <button
              type="button"
              onClick={() => setNewSessionNotice(null)}
              className="text-primary hover:text-white text-xs font-bold px-1.5 py-0.5 rounded cursor-pointer"
            >
              ✕
            </button>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-3.5 text-xs text-rose-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Action Button */}
        <button
          type="submit"
          disabled={!canAnalyze || loading}
          className="w-full bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-background font-black py-3.5 rounded-xl transition-all shadow-xl hover:shadow-primary/20 flex items-center justify-center gap-2 text-base cursor-pointer"
        >
          {loading ? (
            <span>جاري تحليل السعر ومطابقة النموذج الفني...</span>
          ) : (
            <>
              <TrendingUp className="w-5 h-5" />
              <span>تحليل السعر اللحظي وإصدار القرار</span>
            </>
          )}
        </button>
      </form>

      {/* Decision Card Output */}
      {result && (
        <DecisionCard
          result={result}
          arabicName={selectedStock?.arabic_name}
          ownsStock={ownsStock}
          buyPrice={ownsStock && buyPrice ? parseFloat(buyPrice) : undefined}
          sharesOwned={ownsStock && sharesOwned ? parseInt(sharesOwned, 10) : undefined}
          previousPlan={previousPlan}
        />
      )}
    </div>
  );
}

export default function LiveAnalysisPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-sm text-gray-400">جاري تحميل شاشة التحليل...</div>}>
      <LiveAnalysisContent />
    </Suspense>
  );
}