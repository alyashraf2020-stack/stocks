"use client";

import Link from "next/link";
import { StockPlan } from "@/lib/types";
import { Activity, ArrowUpRight, Target, ShieldAlert } from "lucide-react";

const price = (value?: number | null) => value == null ? "—" : value.toFixed(2);
const voteLabel: Record<string, string> = { BUY: "شراء", SELL: "بيع", NEUTRAL: "محايد", UNAVAILABLE: "غير متاح" };
export const ratingColor = (signal?: string) => signal?.includes("BUY") ? "text-emerald-400" : signal?.includes("SELL") ? "text-rose-400" : "text-amber-300";

export default function TechnicalSummaryCard({ report, loading, error }: { report: StockPlan | null; loading: boolean; error: string | null }) {
  if (loading) return <div className="p-6 rounded-2xl bg-surface border border-surfaceBorder text-sm text-gray-400" aria-live="polite">جاري حساب التقييم الفني وخطة السهم...</div>;
  if (error || !report) return <div role="alert" className="p-6 rounded-2xl bg-surface border border-amber-500/30 text-sm text-amber-300">{error || "لم يتوفر التقرير الفني. اضغط تحديث البيانات."}</div>;
  const rating = report.technical_rating;
  const plan = report.trade_plan;
  const metrics = report.plan_metrics;
  const current = report.sessions_behind === 0 && report.listing_status === "ACTIVE";
  const setup = plan?.new_entry_allowed ? "داخل نطاق الدخول عند الإغلاق" : plan ? report.pullback_status_ar : report.status_ar;

  return <section className="space-y-5" aria-label="التقييم الفني وخطة التداول">
    <div className="rounded-2xl border border-emerald-500/25 bg-gradient-to-br from-emerald-950/20 to-surface p-5 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs text-gray-400 mb-2">تقييم فني يومي · {rating?.as_of_session || report.latest_available_session || "لا توجد جلسات"}</p>
          <div className="flex gap-3 items-center"><Activity className="w-6 h-6 text-primary" /><h2 className="text-lg font-black text-white">مؤشر الإشارة الفنية</h2></div>
        </div>
        <span className={`rounded-full border border-current px-4 py-1.5 text-sm font-bold ${current && rating ? ratingColor(rating.signal) : "text-amber-300"}`}>
          {current && rating ? rating.signal_ar : "لا توجد إشارة حالية"}
        </span>
      </div>
      {!current && <p className="text-amber-300 text-sm">{report.reason_ar} {rating && "التقييم أدناه تاريخي بتاريخ الجلسة المعروضة."}</p>}
      {rating ? <>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div><span className={`text-4xl font-black font-mono ${ratingColor(rating.signal)}`} dir="ltr">{rating.score > 0 ? "+" : ""}{rating.score.toFixed(1)}</span><span className="text-xs text-gray-400 mr-3">من ‎−100 إلى ‎+100</span></div>
          <div className="text-sm text-gray-300">اتفاق المؤشرات <strong className="text-white font-mono">{rating.agreement_pct.toFixed(0)}%</strong>
            <p className="text-xs text-gray-500 mt-1">نسبة المؤشرات في اتجاه الإشارة؛ ليست احتمال نجاح الصفقة</p></div>
        </div>
        <div dir="ltr" className="relative h-5 rounded-full bg-gradient-to-r from-rose-600 via-amber-400 to-emerald-500" role="meter" aria-label="درجة الإشارة الفنية" aria-valuemin={-100} aria-valuemax={100} aria-valuenow={rating.score}>
          <span className="absolute -top-1 w-2 h-7 rounded bg-white shadow" style={{ left: `calc(${(rating.score + 100) / 2}% - 4px)` }} />
        </div>
        <div className="flex justify-between text-xs" dir="ltr"><span className="text-rose-400">بيع قوي</span><span className="text-amber-300">محايد</span><span className="text-emerald-400">شراء قوي</span></div>
        <div className="grid grid-cols-3 gap-3 text-center text-xs">
          {[['BUY', 'شراء'], ['NEUTRAL', 'محايد'], ['SELL', 'بيع']].map(([key, label]) => <div key={key} className="bg-background/40 rounded-xl p-3"><span className={ratingColor(key)}>{label}</span><p className="text-xl font-bold font-mono text-white mt-1">{rating.counts[key]}</p></div>)}
        </div>
        <p className="text-xs text-gray-400">محسوب من <strong className="text-white">{rating.available_count} / {rating.total_count}</strong> مؤشر · تغطية {rating.coverage_pct.toFixed(0)}% {rating.status === "PARTIAL" && "· تقييم جزئي: المؤشرات غير المتاحة مستبعدة من الحساب"} · وزن الاتجاه 50% والزخم 50%</p>
        <details className="border-t border-surfaceBorder pt-3">
          <summary className="text-primary text-sm cursor-pointer font-bold">تفاصيل المؤشرات وقواعد الحساب</summary>
          <p className="text-xs text-gray-400 my-3">الدرجة = متوسط درجتي الاتجاه والزخم. كل مؤشر متاح يصوّت ‎+1 أو 0 أو ‎−1؛ المتشابهة قد تكون مترابطة. التصنيف: فوق 50 شراء قوي، فوق 10 شراء، بين ‎−10 و10 محايد، أدنى ‎−10 بيع، أدنى ‎−50 بيع قوي.</p>
          <div className="overflow-x-auto"><table className="w-full min-w-[550px] text-xs text-right">
            <thead className="text-gray-400"><tr>{["المؤشر", "القيمة", "الإشارة", "القاعدة"].map(title => <th key={title} className="p-2">{title}</th>)}</tr></thead>
            <tbody>{rating.indicators.map(item => <tr key={item.key} className="border-t border-surfaceBorder text-gray-300"><td className="p-2 font-mono">{item.key}</td><td className="p-2 font-mono" dir="ltr">{item.value == null ? "—" : item.value.toFixed(3)}</td><td className={`p-2 whitespace-nowrap ${ratingColor(item.signal)}`}>{voteLabel[item.signal]}</td><td className="p-2">{item.rule_ar}{item.vote == null && " · يحتاج تاريخًا أطول أو بيانات حجم صالحة"}</td></tr>)}</tbody>
          </table></div>
        </details>
      </> : <p className="text-sm text-amber-300">{report.reason_ar}</p>}
    </div>

    <div className="rounded-2xl bg-surface border border-surfaceBorder p-5 space-y-4">
      <div className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-black text-white">خطة السهم: تراجع للدعم / إعادة اختبار</h2><span className="text-sm text-amber-300">{setup}</span></div>
      <p className="text-xs text-gray-400">تقييم «شراء» يصف الاتجاه الفني. الدخول يعتمد على نطاق الخطة وشرطه وسعر الوسيط الحالي؛ الإغلاق ليس سعرًا لحظيًا.</p>
      {plan ? <>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4"><p className="text-xs text-primary mb-2">نطاق الدخول · ج.م</p><p className="text-lg font-mono font-black text-white" dir="ltr">{price(plan.entry_zone_min)} – {price(plan.entry_zone_max)}</p></div>
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4"><p className="flex gap-2 text-xs text-rose-400 mb-2"><ShieldAlert className="w-4 h-4" />وقف الخسارة · ج.م</p><p className="text-xl font-mono font-black text-rose-400">{price(plan.stop_loss)}</p></div>
          <div className="rounded-xl border border-surfaceBorder p-4"><p className="text-xs text-gray-400 mb-2">المخاطرة من سعر دخول الخطة</p><p className="text-xl font-mono font-black text-white">{metrics ? `${metrics.risk_pct.toFixed(2)}%` : "—"}</p><p className="text-xs text-gray-500 mt-1">لكل سهم {price(metrics?.risk_per_share)} ج.م</p></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[plan.target_1, plan.target_2, plan.target_3].map((target, i) => <div key={i} className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-4"><p className="text-xs text-emerald-400 mb-2 flex gap-2"><Target className="w-4 h-4" />الهدف {i + 1}</p><p className="text-xl font-black font-mono text-white">{price(target)} <span className="text-xs font-normal">ج.م</span></p>{metrics && <p className="text-xs text-emerald-300 mt-2" dir="ltr">+{metrics.target_gain_pct[i].toFixed(2)}% · {metrics.reward_risk[i].toFixed(2)}R</p>}</div>)}
        </div>
        <details className="text-xs text-gray-400"><summary className="cursor-pointer text-gray-300">سبب مستويات الخطة</summary><div className="pt-3 space-y-2"><p>{plan.entry_basis}</p><p>{plan.stop_basis}</p><p>{plan.trigger_condition}</p><p>العائد والمخاطرة محسوبان من دخول مرجعي {price(metrics?.reference_entry)} ج.م؛ بدون عمولات أو انزلاق سعري. الأهداف مستويات شرطية ولا تحدد موعد تحققها.</p></div></details>
      </> : <p className="text-sm text-amber-300">{report.reason_ar}</p>}
      <div className="flex gap-4 flex-wrap text-sm"><Link href={`/live-analysis?ticker=${report.ticker}`} className="inline-flex items-center gap-1 text-primary font-bold">تحليل بالسعر الحالي من الوسيط<ArrowUpRight className="w-4 h-4" /></Link><Link href="/plans" className="text-gray-400 hover:text-white">مقارنة خطط كل الأسهم والاختراق</Link></div>
    </div>
    {rating && <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-gray-400">
      {[["التقلب اليومي ATR / الإغلاق", `${rating.atr_pct.toFixed(2)}% · ${rating.volatility_ar}`], ["متوسط حجم 20 جلسة", rating.mean_volume_20.toLocaleString("en-US", { maximumFractionDigits: 0 })], ["حجم آخر جلسة / المتوسط", rating.relative_volume == null ? "—" : `${rating.relative_volume.toFixed(2)}×`], ["التاريخ المتاح", `${report.analytical_bars_count} جلسة`]].map(([label, value]) => <div key={label} className="p-4 rounded-xl bg-surface border border-surfaceBorder"><p>{label}</p><p className="font-bold text-white mt-2">{value}</p></div>)}
    </div>}
    <p className="text-xs text-gray-500">{rating?.note_ar || "لا يصدر تقييم بدون تاريخ كافٍ."} {report.missing_sessions_count ? `توجد ${report.missing_sessions_count} جلسة سوق بلا بيانات داخل التاريخ؛ الحسابات تستخدم المتاح فقط.` : ""} · المصدر: {report.actual_provider || "غير متاح"}</p>
  </section>;
}
