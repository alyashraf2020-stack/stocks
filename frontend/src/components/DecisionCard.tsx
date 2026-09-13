"use client";

import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ShieldAlert,
  ArrowUpRight,
  TrendingUp,
  Percent,
  Coins,
  Scale,
  Info,
  CalendarDays,
  Layers3,
} from "lucide-react";
import { LiveAnalysisResult, TradePlan } from "@/lib/types";

interface DecisionCardProps {
  result: LiveAnalysisResult;
  arabicName?: string;
  ownsStock?: boolean;
  buyPrice?: number;
  sharesOwned?: number;
  previousPlan?: TradePlan | null;
}

export default function DecisionCard({
  result,
  arabicName,
  ownsStock: ownsStockProp,
  buyPrice: buyPriceProp,
  sharesOwned: sharesOwnedProp,
  previousPlan,
}: DecisionCardProps) {
  const {
    ticker,
    current_price,
    decision_ar,
    badge_color,
    reason_ar,
    trade_plan,
    position_sizing,
    expected_latest_session,
    latest_available_session,
    sessions_behind,
    actual_provider,
    owner_add_on,
    corporate_events,
    market_depth,
  } = result;

  const isOwner = ownsStockProp !== undefined ? ownsStockProp : Boolean(result.owns_stock);
  const effectiveBuyPrice = buyPriceProp !== undefined ? buyPriceProp : result.buy_price;
  const effectiveSharesOwned = sharesOwnedProp !== undefined ? sharesOwnedProp : result.shares_owned;

  const buyPriceNum = effectiveBuyPrice ? Number(effectiveBuyPrice) : 0;
  const sharesOwnedNum = effectiveSharesOwned ? Number(effectiveSharesOwned) : 0;
  const costBasis = buyPriceNum * sharesOwnedNum;
  const currentValue = current_price * sharesOwnedNum;
  const unrealizedPnL = currentValue - costBasis;
  const unrealizedPnLPercent = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0;
  const isPositivePnL = unrealizedPnL >= 0;
  const isStale = sessions_behind !== undefined && sessions_behind !== null && sessions_behind > 0;

  const getBadgeStyle = () => {
    switch (badge_color) {
      case "green": return { bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400", icon: CheckCircle2, border: "border-emerald-500/40" };
      case "amber": return { bg: "bg-amber-500/10 border-amber-500/30 text-amber-400", icon: Clock, border: "border-amber-500/40" };
      case "blue": return { bg: "bg-blue-500/10 border-blue-500/30 text-blue-400", icon: ArrowUpRight, border: "border-blue-500/40" };
      case "purple": return { bg: "bg-purple-500/10 border-purple-500/30 text-purple-400", icon: TrendingUp, border: "border-purple-500/40" };
      case "teal": return { bg: "bg-teal-500/10 border-teal-500/30 text-teal-400", icon: Coins, border: "border-teal-500/40" };
      case "red": return { bg: "bg-rose-500/10 border-rose-500/30 text-rose-400", icon: XCircle, border: "border-rose-500/40" };
      default: return { bg: "bg-yellow-500/10 border-yellow-500/30 text-yellow-400", icon: AlertTriangle, border: "border-yellow-500/40" };
    }
  };

  const badgeStyle = getBadgeStyle();
  const BadgeIcon = badgeStyle.icon;
  const planStatus = trade_plan?.plan_status || result.plan_status;
  const isNoSetup = planStatus === "NO_VALID_SETUP" || trade_plan?.entry_zone_min == null;
  const isTargetsCompleted = planStatus === "TARGETS_COMPLETED";
  const effectivePreviousPlan = previousPlan || result.previous_plan;

  return (
    <div className={`bg-surface border ${badgeStyle.border} rounded-2xl p-6 shadow-2xl space-y-6 transition-all`}>
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surfaceBorder pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-black text-white">{ticker}</h2>
            {arabicName && <span className="text-sm font-medium text-gray-400">| {arabicName}</span>}
          </div>
          <div className="text-xs text-gray-400 mt-1 flex items-center gap-2">
            <span>السعر اللحظي المدخل:</span>
            <span className="text-base font-bold text-white num-ltr">{current_price.toFixed(2)} ج.م</span>
          </div>
        </div>
        <div className={`flex items-center gap-2.5 px-4 py-2 rounded-xl border ${badgeStyle.bg} text-lg font-black`}>
          <BadgeIcon className="w-6 h-6 flex-shrink-0" />
          <span>{decision_ar}</span>
        </div>
      </div>

      {isStale && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-amber-300 text-sm space-y-2">
          <div className="flex items-center gap-2 font-bold text-base"><AlertTriangle className="w-5 h-5" /><span>بيانات آخر جلسة غير متاحة</span></div>
          <p className="text-xs leading-relaxed text-gray-300">لا يمكن إصدار توصية دخول حالية حتى وصول بيانات آخر جلسة مكتملة وفق سياسة انعدام التأخير.</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs border-t border-amber-500/20 text-gray-400">
            <div>آخر جلسة متاحة: <span className="font-mono text-white num-ltr">{latest_available_session || "—"}</span></div>
            <div>آخر جلسة مطلوبة: <span className="font-mono text-white num-ltr">{expected_latest_session || "—"}</span></div>
            <div>الجلسات المتأخرة: <span className="font-bold text-amber-400 num-ltr">{sessions_behind} جلسة</span></div>
            <div>المصدر الحالي: <span className="text-gray-300">{actual_provider || "—"}</span></div>
          </div>
        </div>
      )}

      <div className="bg-surfaceHover border border-surfaceBorder rounded-xl p-4">
        <div className="flex items-center gap-2 text-xs font-bold text-primary mb-1"><Info className="w-4 h-4" /><span>لماذا هذا القرار؟</span></div>
        <p className="text-sm text-gray-200 leading-relaxed">{reason_ar}</p>
      </div>

      {isOwner && owner_add_on && (
        <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-bold text-cyan-300"><ArrowUpRight className="w-4 h-4" /><span>قرار التعزيز للمركز الحالي</span></div>
            <span className={`text-xs font-black px-3 py-1 rounded-full border ${owner_add_on.decision === "ADD_NOW" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" : "bg-amber-500/10 text-amber-400 border-amber-500/30"}`}>{owner_add_on.decision_ar}</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">{owner_add_on.reason_ar}</p>
          {owner_add_on.entry_zone_min != null && owner_add_on.entry_zone_max != null && (
            <div className="text-xs text-gray-400">منطقة التعزيز الحالية: <strong className="text-white num-ltr">{owner_add_on.entry_zone_min.toFixed(2)} – {owner_add_on.entry_zone_max.toFixed(2)} ج.م</strong></div>
          )}
          {owner_add_on.sizing && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
              <Metric label="أسهم التعزيز القصوى" value={`${owner_add_on.sizing.suggested_add_on_shares.toLocaleString()} سهم`} accent="text-cyan-300" />
              <Metric label="قيمة التعزيز التقريبية" value={`${owner_add_on.sizing.estimated_add_on_value_egp.toLocaleString()} ج.م`} />
              <Metric label="التخصيص المتبقي" value={`${owner_add_on.sizing.remaining_allocation_egp.toLocaleString()} ج.م`} />
              <Metric label="ميزانية المخاطرة المتبقية" value={`${owner_add_on.sizing.remaining_risk_budget_egp.toLocaleString()} ج.م`} />
            </div>
          )}
        </div>
      )}

      {corporate_events && corporate_events.length > 0 && (
        <div className="bg-violet-500/5 border border-violet-500/20 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-violet-300"><CalendarDays className="w-4 h-4" /><span>أحداث وأخبار شركة مهمة</span></div>
          {corporate_events.map((event) => (
            <div key={`${event.event_type}-${event.event_date}`} className="bg-surface/70 border border-surfaceBorder rounded-lg p-3 space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-bold text-white">{event.title_ar}</span><span className="text-xs font-mono text-violet-300 num-ltr">{event.event_date}</span></div>
              <p className="text-xs text-gray-300 leading-relaxed">{event.summary_ar}</p>
              <div className="text-[11px] text-gray-500">تأثير متوقع: غير مؤكد — لا يُستخدم الخبر وحده كإشارة شراء.</div>
              <a href={event.source_url} target="_blank" rel="noreferrer" className="text-[11px] text-primary hover:underline">المصدر: {event.source_name}</a>
            </div>
          ))}
        </div>
      )}

      {market_depth && (
        <div className="bg-surfaceHover/40 border border-surfaceBorder rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2 text-sm font-bold text-gray-300"><Layers3 className="w-4 h-4 text-primary" /><span>عمق السوق — شراء مقابل بيع</span></div><span className="text-xs text-gray-400">{market_depth.pressure_ar}</span></div>
          {market_depth.status === "MANUAL_INPUT" ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center">
              <Metric label="إجمالي الشراء" value={`${(market_depth.buy_qty || 0).toLocaleString()} سهم`} accent="text-emerald-400" />
              <Metric label="إجمالي البيع" value={`${(market_depth.sell_qty || 0).toLocaleString()} سهم`} accent="text-rose-400" />
              <Metric label="اختلال العرض/الطلب" value={`${(market_depth.imbalance_pct || 0) >= 0 ? "+" : ""}${(market_depth.imbalance_pct || 0).toFixed(2)}%`} />
            </div>
          ) : (
            <div className="text-xs text-gray-400">عمق السوق اللحظي غير متصل تلقائيًا حاليًا. أدخل إجمالي أوامر الشراء والبيع من شاشة الوسيط، أو اربط Feed Level-2 معتمد.</div>
          )}
          <p className="text-[11px] text-gray-500">{market_depth.note_ar}</p>
        </div>
      )}

      {trade_plan && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2"><Scale className={`w-4 h-4 ${isNoSetup || isTargetsCompleted ? "text-amber-400" : "text-primary"}`} /><span>{isNoSetup ? "الخطة الحالية" : isTargetsCompleted ? "الخطة السابقة — اكتملت أهدافها" : effectivePreviousPlan ? "الخطة الحالية (Long-Only Setup)" : "خطة التداول المحددة (Long-Only Setup)"}</span></h3>
            {isNoSetup && <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400">لا توجد فرصة دخول صالحة حاليًا</span>}
            {isTargetsCompleted && <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400">انتظار فرصة دخول جديدة</span>}
          </div>

          {isNoSetup ? (
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4 text-center space-y-1"><span className="text-sm font-bold text-amber-400 block">لا توجد فرصة دخول صالحة حاليًا</span><span className="text-xs text-gray-400 block">انتظر تكوين إعداد فني جديد من البيانات القادمة بعد اكتمال الأهداف السابقة والتمدد السعري.</span></div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className={`${isTargetsCompleted ? "bg-amber-500/5 border-amber-500/20" : "bg-surfaceHover/70 border-surfaceBorder"} border rounded-xl p-3`}>
                <span className={`text-[11px] block mb-1 ${isTargetsCompleted ? "text-amber-400 font-bold" : "text-gray-400"}`}>{isTargetsCompleted ? "لا توجد منطقة دخول حالية" : "منطقة الدخول الآمنة"}</span>
                <span className="text-sm font-bold text-white num-ltr">{trade_plan.entry_zone_min != null && trade_plan.entry_zone_max != null ? `${trade_plan.entry_zone_min.toFixed(2)} – ${trade_plan.entry_zone_max.toFixed(2)} ج.م` : "—"}</span>
              </div>
              <PlanMetric label="وقف الخسارة" value={trade_plan.stop_loss} className="text-rose-300" />
              <PlanMetric label="الهدف الأول +1.5R" value={trade_plan.target_1} />
              <PlanMetric label="الهدف الثاني +2.5R" value={trade_plan.target_2} />
              <PlanMetric label="الهدف الثالث +3.5R" value={trade_plan.target_3} />
            </div>
          )}
        </div>
      )}

      {effectivePreviousPlan && (
        <div className="bg-surfaceHover/30 border border-surfaceBorder/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between"><h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2"><Clock className="w-4 h-4" /><span>الخطة السابقة (سياق تاريخي)</span></h3><span className="text-[11px] text-gray-500">للمقارنة فقط</span></div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
            <Metric label="منطقة الدخول السابقة" value={effectivePreviousPlan.entry_zone_min != null && effectivePreviousPlan.entry_zone_max != null ? `${effectivePreviousPlan.entry_zone_min.toFixed(2)} – ${effectivePreviousPlan.entry_zone_max.toFixed(2)} ج.م` : "—"} />
            <Metric label="وقف الخسارة السابق" value={effectivePreviousPlan.stop_loss != null ? `${effectivePreviousPlan.stop_loss.toFixed(2)} ج.م` : "—"} accent="text-rose-400/80" />
            <Metric label="الهدف الأول السابق" value={effectivePreviousPlan.target_1 != null ? `${effectivePreviousPlan.target_1.toFixed(2)} ج.م` : "—"} />
            <Metric label="الهدف الثاني السابق" value={effectivePreviousPlan.target_2 != null ? `${effectivePreviousPlan.target_2.toFixed(2)} ج.م` : "—"} />
            <Metric label="الهدف الثالث السابق" value={effectivePreviousPlan.target_3 != null ? `${effectivePreviousPlan.target_3.toFixed(2)} ج.م` : "—"} />
          </div>
        </div>
      )}

      {isOwner && (
        <div className="bg-surfaceHover/40 border border-surfaceBorder rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between"><h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2"><Coins className="w-4 h-4 text-primary" /><span>تفاصيل المركز الحالي</span></h3>{sharesOwnedNum > 0 && buyPriceNum > 0 && <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${isPositivePnL ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" : "bg-rose-500/10 text-rose-400 border border-rose-500/30"}`}>{isPositivePnL ? "ربح غير محقق" : "خسارة غير محققة"}</span>}</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-center">
            <Metric label="عدد الأسهم المملوكة" value={sharesOwnedNum > 0 ? `${sharesOwnedNum.toLocaleString()} سهم` : "—"} />
            <Metric label="متوسط سعر الشراء" value={buyPriceNum > 0 ? `${buyPriceNum.toFixed(2)} ج.م` : "—"} />
            <Metric label="إجمالي تكلفة الشراء" value={costBasis > 0 ? `${costBasis.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ج.م` : "—"} />
            <Metric label="القيمة الحالية للمركز" value={sharesOwnedNum > 0 ? `${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ج.م` : "—"} />
            <Metric label="الربح / الخسارة الحالية" value={costBasis > 0 ? `${unrealizedPnL >= 0 ? "+" : ""}${unrealizedPnL.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ج.م` : "—"} accent={isPositivePnL ? "text-emerald-400" : "text-rose-400"} />
            <Metric label="نسبة الربح / الخسارة" value={costBasis > 0 ? `${unrealizedPnLPercent >= 0 ? "+" : ""}${unrealizedPnLPercent.toFixed(2)}%` : "—"} accent={isPositivePnL ? "text-emerald-400" : "text-rose-400"} />
          </div>
        </div>
      )}

      {!isOwner && position_sizing && (
        <div className="bg-surfaceHover/40 border border-surfaceBorder rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between"><h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2"><ShieldAlert className="w-4 h-4 text-warning" /><span>إدارة المخاطر وتحديد حجم الصفقة</span></h3><span className="text-[11px] text-gray-400">أقصى مخاطرة 1.5% | أقصى تخصيص 20%</span></div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <Metric label="عدد الأسهم المقترح" value={`${position_sizing.suggested_shares.toLocaleString()} سهم`} accent="text-primary" />
            <Metric label="قيمة الصفقة الإجمالية" value={`${position_sizing.position_value_egp.toLocaleString()} ج.م`} />
            <Metric label="أقصى خسارة متوقعة" value={`${position_sizing.max_expected_loss_egp.toLocaleString()} ج.م`} accent="text-rose-400" />
            <Metric label="رأس المال المعتمد" value={`${position_sizing.capital.toLocaleString()} ج.م`} />
          </div>
        </div>
      )}

      {trade_plan && trade_plan.factor_score != null && trade_plan.factor_breakdown && (
        <div className="border-t border-surfaceBorder pt-4 space-y-3">
          <div className="flex items-center justify-between text-xs"><span className="text-gray-400 flex items-center gap-1.5 font-bold"><Percent className="w-4 h-4 text-accent" /><span>قوة التحليل الفني التراكمية:</span><span className="text-white font-bold">{trade_plan.factor_score} / 100</span>{trade_plan.analysis_strength && <span className="text-gray-500">({trade_plan.analysis_strength})</span>}</span><span className="text-[11px] text-gray-500">مؤشر إرشادي فقط ولا يمنح إشارة شراء بمفرده</span></div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {Object.entries(trade_plan.factor_breakdown).map(([key, val]) => {
              const labels: Record<string, string> = { trend: "الاتجاه (Trend)", momentum: "الزخم (Momentum)", price_structure: "هيكل السعر (Structure)", liquidity_volatility: "السيولة والتقلب (Liquidity)" };
              return <div key={key} className="bg-surfaceHover/50 border border-surfaceBorder rounded-lg p-2"><div className="flex justify-between text-[11px] mb-1"><span className="text-gray-400">{labels[key] || key}</span><span className="font-bold text-white">{val}/25</span></div><div className="w-full bg-surfaceBorder h-1.5 rounded-full overflow-hidden"><div className="bg-primary h-full rounded-full transition-all duration-500" style={{ width: `${(val / 25) * 100}%` }} /></div></div>;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, accent = "text-white" }: { label: string; value: string; accent?: string }) {
  return <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5"><span className="text-[11px] text-gray-400 block mb-0.5">{label}</span><span className={`text-sm font-bold num-ltr ${accent}`}>{value}</span></div>;
}

function PlanMetric({ label, value, className = "text-white" }: { label: string; value?: number | null; className?: string }) {
  return <div className="bg-surfaceHover/70 border border-surfaceBorder rounded-xl p-3"><span className="text-[11px] text-gray-400 block mb-1">{label}</span><span className={`text-sm font-bold num-ltr ${className}`}>{value != null ? `${value.toFixed(2)} ج.م` : "—"}</span></div>;
}
