"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ListChecks, RefreshCw, Search, StopCircle, ChevronDown, ChevronUp, ArrowUpRight } from "lucide-react";
import { getAllStockPlans, refreshStockPlan } from "@/lib/api";
import { StockPlan } from "@/lib/types";

const needsData = (row: StockPlan) => row.listing_status === "ACTIVE" &&
  ["DATA_UNAVAILABLE", "DATA_NOT_CURRENT", "INSUFFICIENT_DATA", "ERROR"].includes(row.status);
const money = (value?: number | null) => value == null || !Number.isFinite(value) ? "—" : value.toFixed(2);
const normalize = (value: string) => value.toLowerCase().replace(/[إأآ]/g, "ا")
  .replace(/ة/g, "ه").replace(/ى/g, "ي").replace(/[\u064B-\u0652]/g, "").trim();

export default function AllStockPlansPage() {
  const [rows, setRows] = useState<StockPlan[]>([]);
  const [session, setSession] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("");
  const [filter, setFilter] = useState("all");
  const [scenario, setScenario] = useState<"pullback" | "breakout">("pullback");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [updating, setUpdating] = useState<string[]>([]);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const refreshController = useRef<AbortController | null>(null);
  const generation = useRef(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAllStockPlans(signal);
      if (!signal?.aborted) {
        setRows(data.items);
        setSession(data.expected_latest_session);
      }
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : "تعذر تحميل الخطط");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => {
      controller.abort();
      generation.current += 1;
      refreshController.current?.abort();
    };
  }, [load]);

  const refreshRows = async (targets: StockPlan[]) => {
    if (running || !targets.length) return;
    const controller = new AbortController();
    refreshController.current = controller;
    const thisGeneration = ++generation.current;
    setRunning(true);
    setProgress({ completed: 0, total: targets.length });
    let cursor = 0;
    const worker = async () => {
      while (!controller.signal.aborted && cursor < targets.length) {
        const row = targets[cursor++];
        setUpdating((old) => [...old, row.ticker]);
        setRowErrors((old) => { const next = { ...old }; delete next[row.ticker]; return next; });
        try {
          const updated = await refreshStockPlan(row.ticker, controller.signal);
          if (thisGeneration === generation.current) {
            setRows((old) => old.map((item) => item.ticker === updated.ticker ? updated : item));
          }
        } catch (err) {
          if (thisGeneration === generation.current && !controller.signal.aborted) {
            setRowErrors((old) => ({ ...old, [row.ticker]: err instanceof Error ? err.message : "تعذر التحديث" }));
          }
        } finally {
          if (thisGeneration === generation.current) {
            setUpdating((old) => old.filter((ticker) => ticker !== row.ticker));
            setProgress((old) => ({ ...old, completed: old.completed + 1 }));
          }
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, targets.length) }, worker));
    if (thisGeneration === generation.current) {
      setRunning(false);
      setUpdating([]);
    }
  };

  const stop = () => {
    generation.current += 1;
    refreshController.current?.abort();
    setRunning(false);
    setUpdating([]);
  };

  const sectors = useMemo(() => Array.from(new Set(rows.map((row) => row.sector))).sort(), [rows]);
  const pending = rows.filter(needsData);
  const available = rows.filter((row) => scenario === "pullback" ? !!row.trade_plan : !!row.breakout_entry);
  const visible = rows.filter((row) => {
    const plan = scenario === "pullback" ? row.trade_plan : row.breakout_entry;
    const matchesSearch = !search || normalize(`${row.ticker} ${row.arabic_name} ${row.english_name}`).includes(normalize(search));
    return matchesSearch && (!sector || sector === row.sector) &&
      (filter === "all" || (filter === "ready" && !!plan) || (filter === "needs-data" && needsData(row)) ||
        (filter === "in-zone" && scenario === "pullback" && row.trade_plan?.plan_status === "ACTIVE"));
  });
  const controlClass = "w-full bg-surface border border-surfaceBorder rounded-xl px-3 py-3 text-sm text-white focus:outline-none focus:border-primary";

  return <div className="space-y-6">
    <div className="flex flex-wrap justify-between items-start gap-4 border-b border-surfaceBorder pb-5">
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-black text-white flex items-center gap-3"><ListChecks className="text-primary w-8 h-8" />خطط كل الأسهم</h1>
        <p className="text-sm text-gray-400">نطاق الدخول ووقف الخسارة والأهداف لكل سهم، من بيانات آخر جلسة مكتملة.</p>
        {session && <p className="text-xs text-gray-400">الجلسة المطلوبة: <span className="font-mono text-white">{session}</span> · الأسعار بالجنيه المصري</p>}
      </div>
      <div className="flex gap-2 flex-wrap">
        <button type="button" onClick={() => load()} disabled={loading || running}
          className="px-3 py-2.5 rounded-xl border border-surfaceBorder text-sm text-gray-300 hover:text-white disabled:opacity-50">إعادة حساب المحفوظ</button>
        {running ? <button type="button" onClick={stop} className="flex gap-2 items-center px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm font-bold"><StopCircle className="w-4 h-4" />إيقاف التحديث</button> :
          <button type="button" onClick={() => refreshRows(pending)} disabled={loading || !pending.length}
            className="flex gap-2 items-center px-4 py-2.5 rounded-xl bg-primary text-background text-sm font-bold disabled:opacity-40"><RefreshCw className="w-4 h-4" />جلب البيانات الناقصة ({pending.length})</button>}
      </div>
    </div>

    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {[["الأسهم في الدليل", rows.length], ["خطط هذا السيناريو", available.length], ["تحتاج بيانات", pending.length], ["النتائج المعروضة", visible.length]].map(([label, count]) =>
        <div key={label} className="bg-surface border border-surfaceBorder rounded-xl p-4"><p className="text-xs text-gray-400 mb-1">{label}</p><p className="text-2xl text-white font-black font-mono">{count}</p></div>)}
    </div>

    <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 text-sm text-gray-300 space-y-2">
      <p><span className="text-primary font-bold">كيف تستخدم الخطة؟</span> اختر سيناريو التراجع للدعم أو الاختراق، وراقب نطاق الدخول ووقفه والأهداف. آخر إغلاق مرجع للحساب وليس سعرًا لحظيًا أو أمر شراء.</p>
      <p className="text-xs text-gray-400">الخطط المحفوظة تُحسب تلقائيًا عند فتح الصفحة. جلب البيانات الناقصة يتم على دفعات ويظهر تدريجيًا؛ الأسهم غير المحدثة تبقى في الجدول مع سبب عدم إصدار خطة.</p>
    </div>

    {(running || progress.total > 0) && <div aria-live="polite" className="bg-surface border border-surfaceBorder rounded-xl p-4 space-y-2">
      <div className="flex justify-between text-xs text-gray-300"><span>{running ? `جاري فحص: ${updating.join("، ") || "..."}` : progress.completed === progress.total ? "اكتمل فحص الدفعة؛ راجع حالة البيانات في كل صف" : "تم إيقاف الدفعة"}</span><span className="font-mono">{progress.completed} / {progress.total}</span></div>
      <progress value={progress.completed} max={progress.total || 1} className="w-full h-2 accent-emerald-500" />
    </div>}

    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <label className="text-xs text-gray-400 space-y-1"><span>سيناريو الدخول</span><select value={scenario} onChange={(event) => { setScenario(event.target.value as "pullback" | "breakout"); setFilter("all"); }} className={controlClass}>
        <option value="pullback">تراجع للدعم / إعادة اختبار</option><option value="breakout">اختراق المقاومة</option>
      </select></label>
      <label className="text-xs text-gray-400 space-y-1"><span>بحث بالاسم أو الرمز</span><div className="relative"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="مثال: MBSC أو مصر بني سويف" className={controlClass + " pl-9"} /><Search className="absolute left-3 top-3.5 w-4 h-4" /></div></label>
      <label className="text-xs text-gray-400 space-y-1"><span>القطاع</span><select value={sector} onChange={(event) => setSector(event.target.value)} className={controlClass}><option value="">كل القطاعات</option>{sectors.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label className="text-xs text-gray-400 space-y-1"><span>حالة الخطة</span><select value={filter} onChange={(event) => setFilter(event.target.value)} className={controlClass}><option value="all">كل الأسهم</option><option value="ready">لها خطة في هذا السيناريو</option><option value="needs-data">تحتاج جلب بيانات</option>{scenario === "pullback" && <option value="in-zone">داخل نطاق الدخول عند الإغلاق</option>}</select></label>
    </div>

    {error && <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-300 p-4 text-sm">{error}</div>}
    <div className="bg-surface border border-surfaceBorder rounded-2xl overflow-hidden">
      {loading ? <div className="p-12 text-center text-sm text-gray-400">جاري حساب خطط الأسهم من البيانات المحفوظة...</div> : error && !rows.length ?
        <div className="p-8 text-center text-gray-400 text-sm">اضغط «إعادة حساب المحفوظ» بعد تشغيل الباك إند.</div> : !visible.length ?
        <div className="p-12 text-center text-gray-400 text-sm">لا توجد نتائج مطابقة للبحث والفلاتر.</div> :
        <div className="overflow-x-auto"><table className="w-full min-w-[1100px] text-right text-xs divide-y divide-surfaceBorder">
          <thead className="bg-surfaceHover text-gray-400"><tr>{["السهم", "آخر إغلاق", "نطاق الدخول", "وقف الخسارة", "هدف 1", "هدف 2", "هدف 3", "حالة الخطة", "جلسة الحساب", "الإجراءات"].map((title) => <th key={title} className="px-3 py-4 whitespace-nowrap">{title}</th>)}</tr></thead>
          <tbody className="divide-y divide-surfaceBorder">{visible.map((row) => {
            const plan = scenario === "pullback" ? row.trade_plan : row.breakout_entry;
            const isUpdating = updating.includes(row.ticker);
            const isExpanded = expanded === row.ticker;
            const condition = !plan ? row.status === "PLAN_AVAILABLE" ? "لا توجد خطة لهذا السيناريو" : row.status_ar :
              scenario === "pullback" ? row.pullback_status_ar : "راقب تأكيد الاختراق";
            return <Fragment key={row.ticker}>
              <tr className="hover:bg-surfaceHover/50 text-gray-300">
                <td className="px-3 py-4 max-w-[190px]"><Link href={`/stocks/${row.ticker}`} className="font-black text-white font-mono text-sm hover:text-primary">{row.ticker}</Link><div className="mt-1 text-[11px] text-gray-400">{row.arabic_name}</div></td>
                <td className="px-3 py-4 font-mono num-ltr text-white">{money(row.latest_close)}</td>
                <td className="px-3 py-4"><span className="font-mono num-ltr font-bold text-primary whitespace-nowrap">{plan ? `${money(plan.entry_zone_min)} – ${money(plan.entry_zone_max)}` : "—"}</span>{scenario === "breakout" && plan && <p className="text-[10px] text-gray-500 mt-1">بعد اختراق المقاومة</p>}</td>
                <td className="px-3 py-4 font-mono num-ltr font-bold text-rose-400">{money(plan?.stop_loss)}</td>
                {[plan?.target_1, plan?.target_2, plan?.target_3].map((value, index) => <td key={index} className="px-3 py-4 font-mono num-ltr text-emerald-300">{money(value)}</td>)}
                <td className="px-3 py-4 max-w-[160px]"><span className={`text-[11px] ${plan ? "text-emerald-300" : "text-amber-300"}`}>{condition}</span>{rowErrors[row.ticker] && <p className="text-rose-400 mt-1 text-[10px]">{rowErrors[row.ticker]}</p>}</td>
                <td className="px-3 py-4 font-mono text-[11px] text-gray-400">{row.latest_available_session || "—"}</td>
                <td className="px-3 py-4"><div className="flex gap-1">
                  <button type="button" onClick={() => setExpanded(isExpanded ? null : row.ticker)} aria-label={`تفاصيل خطة ${row.ticker}`} aria-expanded={isExpanded} className="p-2 bg-surfaceHover rounded-lg hover:text-white">{isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</button>
                  <button type="button" onClick={() => refreshRows([row])} disabled={running || row.listing_status !== "ACTIVE"} aria-label={`تحديث خطة ${row.ticker}`} className="p-2 bg-surfaceHover rounded-lg hover:text-primary disabled:opacity-40"><RefreshCw className={`w-4 h-4 ${isUpdating ? "animate-spin text-primary" : ""}`} /></button>
                </div></td>
              </tr>
              {isExpanded && <tr><td colSpan={10} className="p-5 bg-background/30"><div className="space-y-3 text-gray-300">
                <p>{row.reason_ar}</p>
                {scenario === "pullback" && row.trade_plan && <><p>{row.trade_plan.entry_basis}</p><p className="text-rose-300">{row.trade_plan.stop_basis}</p><p>{row.trade_plan.trigger_condition}</p></>}
                {scenario === "breakout" && row.breakout_entry && <><p>{row.breakout_entry.reason_ar}</p><p>{row.breakout_entry.confirmation_ar}</p></>}
                <p className="text-gray-500">المصدر: {row.actual_provider || "غير متاح"} · الجلسات الصالحة: {row.analytical_bars_count} · الجلسة المطلوبة: {row.expected_latest_session}</p>
                <div className="flex flex-wrap gap-3"><Link href={`/live-analysis?ticker=${row.ticker}`} className="inline-flex items-center gap-1 text-primary font-bold">قارن الخطة بسعر الوسيط الحالي<ArrowUpRight className="w-4 h-4" /></Link><Link href={`/stocks/${row.ticker}`} className="text-gray-400 hover:text-white">عرض التفاصيل والشارت</Link></div>
              </div></td></tr>}
            </Fragment>;
          })}</tbody>
        </table></div>}
    </div>
    <p className="text-xs text-gray-500">أهداف الخطة مستويات حسابية مرتبطة بالمخاطرة. التنفيذ الفعلي ووقف الخسارة قد يتأثران بالسيولة والانزلاق السعري.</p>
  </div>;
}
