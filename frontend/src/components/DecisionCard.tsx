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
  Info
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
    decision,
    decision_ar,
    badge_color,
    reason_ar,
    trade_plan,
    position_sizing,
    expected_latest_session,
    latest_available_session,
    sessions_behind,
    actual_provider
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

  // Visual decision color maps
  const getBadgeStyle = () => {
    switch (badge_color) {
      case "green":
        return {
          bg: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
          icon: CheckCircle2,
          border: "border-emerald-500/40",
        };
      case "amber":
        return {
          bg: "bg-amber-500/10 border-amber-500/30 text-amber-400",
          icon: Clock,
          border: "border-amber-500/40",
        };
      case "blue":
        return {
          bg: "bg-blue-500/10 border-blue-500/30 text-blue-400",
          icon: ArrowUpRight,
          border: "border-blue-500/40",
        };
      case "purple":
        return {
          bg: "bg-purple-500/10 border-purple-500/30 text-purple-400",
          icon: TrendingUp,
          border: "border-purple-500/40",
        };
      case "teal":
        return {
          bg: "bg-teal-500/10 border-teal-500/30 text-teal-400",
          icon: Coins,
          border: "border-teal-500/40",
        };
      case "red":
        return {
          bg: "bg-rose-500/10 border-rose-500/30 text-rose-400",
          icon: XCircle,
          border: "border-rose-500/40",
        };
      default:
        return {
          bg: "bg-yellow-500/10 border-yellow-500/30 text-yellow-400",
          icon: AlertTriangle,
          border: "border-yellow-500/40",
        };
    }
  };

  const badgeStyle = getBadgeStyle();
  const BadgeIcon = badgeStyle.icon;

  const planStatus = trade_plan?.plan_status || result.plan_status;
  const isNoSetup =
    planStatus === "NO_VALID_SETUP" ||
    trade_plan?.entry_zone_min === null ||
    trade_plan?.entry_zone_min === undefined;
  const isTargetsCompleted = planStatus === "TARGETS_COMPLETED";
  const effectivePreviousPlan = previousPlan || result.previous_plan;

  return (
    <div className={`bg-surface border ${badgeStyle.border} rounded-2xl p-6 shadow-2xl space-y-6 transition-all`}>
      {/* Card Header */}
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

        {/* Prominent Decision Badge */}
        <div className={`flex items-center gap-2.5 px-4 py-2 rounded-xl border ${badgeStyle.bg} text-lg font-black`}>
          <BadgeIcon className="w-6 h-6 flex-shrink-0" />
          <span>{decision_ar}</span>
        </div>
      </div>

      {/* Zero-Session-Lag Warning Banner if Stale */}
      {isStale && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-amber-300 text-sm space-y-2">
          <div className="flex items-center gap-2 font-bold text-base">
            <AlertTriangle className="w-5 h-5 flex-shrink-0 text-amber-400" />
            <span>⚠️ بيانات آخر جلسة غير متاحة</span>
          </div>
          <p className="text-xs leading-relaxed text-gray-300">
            لا يمكن إصدار توصية دخول حالية حتى وصول بيانات آخر جلسة مكتملة وفقاً لسياسة انعدام التأخير (Zero-Session-Lag).
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs border-t border-amber-500/20 text-gray-400">
            <div>آخر جلسة متاحة: <span className="font-mono text-white num-ltr">{latest_available_session || "—"}</span></div>
            <div>آخر جلسة مطلوبة: <span className="font-mono text-white num-ltr">{expected_latest_session || "—"}</span></div>
            <div>الجلسات المتأخرة: <span className="font-bold text-amber-400 num-ltr">{sessions_behind} جلسة</span></div>
            <div>المصدر الحالي: <span className="text-gray-300">{actual_provider || "—"}</span></div>
          </div>
        </div>
      )}

      {/* "لماذا؟" (Reasoning Section) */}
      <div className="bg-surfaceHover border border-surfaceBorder rounded-xl p-4">
        <div className="flex items-center gap-2 text-xs font-bold text-primary mb-1">
          <Info className="w-4 h-4" />
          <span>لماذا هذا القرار؟</span>
        </div>
        <p className="text-sm text-gray-200 leading-relaxed">{reason_ar}</p>
      </div>

      {/* Analytical Setup Grid (If available) */}
      {trade_plan && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Scale className={`w-4 h-4 ${isNoSetup || isTargetsCompleted ? "text-amber-400" : "text-primary"}`} />
              <span>
                {isNoSetup
                  ? "الخطة الحالية"
                  : isTargetsCompleted
                  ? "الخطة السابقة — اكتملت أهدافها"
                  : effectivePreviousPlan
                  ? "الخطة الحالية (Long-Only Setup)"
                  : "خطة التداول المحددة (Long-Only Setup)"}
              </span>
            </h3>
            {isNoSetup ? (
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400">
                لا توجد فرصة دخول صالحة حاليًا
              </span>
            ) : isTargetsCompleted ? (
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400">
                انتظار فرصة دخول جديدة
              </span>
            ) : null}
          </div>

          {isNoSetup ? (
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4 text-center space-y-1">
              <span className="text-sm font-bold text-amber-400 block">
                لا توجد فرصة دخول صالحة حاليًا
              </span>
              <span className="text-xs text-gray-400 block">
                انتظر تكوين إعداد فني جديد من البيانات القادمة بعد اكتمال الأهداف السابقة والتمدد السعري.
              </span>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {/* Entry Zone */}
              {isTargetsCompleted ? (
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3">
                  <span className="text-[11px] text-amber-400 font-bold block mb-1">
                    لا توجد منطقة دخول حالية
                  </span>
                  <span className="text-xs text-gray-300 block leading-snug">
                    الخطة السابقة اكتملت بعد تجاوز الهدف الثالث.
                  </span>
                  {trade_plan.entry_zone_min != null && trade_plan.entry_zone_max != null && (
                    <span className="text-[10px] text-gray-500 block mt-2 pt-1.5 border-t border-surfaceBorder/80">
                      منطقة دخول الخطة السابقة: {trade_plan.entry_zone_min.toFixed(2)} – {trade_plan.entry_zone_max.toFixed(2)} ج.م
                    </span>
                  )}
                </div>
              ) : (
                <div className="bg-surfaceHover/70 border border-surfaceBorder rounded-xl p-3">
                  <span className="text-[11px] text-gray-400 block mb-1">منطقة الدخول الآمنة</span>
                  <span className="text-sm font-bold text-white num-ltr">
                    {trade_plan.entry_zone_min != null && trade_plan.entry_zone_max != null
                      ? `${trade_plan.entry_zone_min.toFixed(2)} – ${trade_plan.entry_zone_max.toFixed(2)} ج.م`
                      : "—"}
                  </span>
                  <span className="text-[10px] text-gray-500 block mt-1">
                    سعر التخطيط: {trade_plan.planning_entry != null ? trade_plan.planning_entry.toFixed(2) : "—"}
                  </span>
                </div>
              )}

              {/* Stop Loss */}
              <div className="bg-rose-500/5 border border-rose-500/20 rounded-xl p-3">
                <span className="text-[11px] text-rose-400 block mb-1">وقف الخسارة (إبطال السيناريو)</span>
                <span className="text-sm font-bold text-rose-300 num-ltr">
                  {trade_plan.stop_loss != null ? `${trade_plan.stop_loss.toFixed(2)} ج.م` : "—"}
                </span>
                <span className="text-[10px] text-gray-500 block mt-1">
                  مخاطرة السهم: R = {trade_plan.r_unit != null ? trade_plan.r_unit.toFixed(2) : "—"}
                </span>
              </div>

              {/* Target 1 */}
              <div className="bg-surfaceHover/70 border border-surfaceBorder rounded-xl p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-gray-400">الهدف الأول</span>
                  <span className="text-[10px] text-primary font-mono font-bold">+1.5R</span>
                </div>
                <span className="text-sm font-bold text-white num-ltr">
                  {trade_plan.target_1 != null ? `${trade_plan.target_1.toFixed(2)} ج.م` : "—"}
                </span>
                <span className="text-[10px] text-gray-500 block mt-1">عائد/مخاطرة: 1 : 1.5</span>
              </div>

              {/* Target 2 */}
              <div className="bg-surfaceHover/70 border border-surfaceBorder rounded-xl p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-gray-400">الهدف الثاني</span>
                  <span className="text-[10px] text-primary font-mono font-bold">+2.5R</span>
                </div>
                <span className="text-sm font-bold text-white num-ltr">
                  {trade_plan.target_2 != null ? `${trade_plan.target_2.toFixed(2)} ج.م` : "—"}
                </span>
                <span className="text-[10px] text-gray-500 block mt-1">عائد/مخاطرة: 1 : 2.5</span>
              </div>

              {/* Target 3 */}
              <div className="bg-surfaceHover/70 border border-surfaceBorder rounded-xl p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-gray-400">الهدف الثالث</span>
                  <span className="text-[10px] text-primary font-mono font-bold">+3.5R</span>
                </div>
                <span className="text-sm font-bold text-white num-ltr">
                  {trade_plan.target_3 != null ? `${trade_plan.target_3.toFixed(2)} ج.م` : "—"}
                </span>
                <span className="text-[10px] text-gray-500 block mt-1">عائد/مخاطرة: 1 : 3.5</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Previous Plan (Historical Context) */}
      {effectivePreviousPlan && (
        <div className="bg-surfaceHover/30 border border-surfaceBorder/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-400" />
              <span>الخطة السابقة (سياق تاريخي)</span>
            </h3>
            <span className="text-[11px] text-gray-500">
              خطة الجلسة السابقة للمقارنة الفنية
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">منطقة الدخول السابقة</span>
              <span className="text-xs font-bold text-gray-300 num-ltr">
                {effectivePreviousPlan.entry_zone_min != null && effectivePreviousPlan.entry_zone_max != null
                  ? `${effectivePreviousPlan.entry_zone_min.toFixed(2)} – ${effectivePreviousPlan.entry_zone_max.toFixed(2)} ج.م`
                  : "—"}
              </span>
            </div>
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">وقف الخسارة السابق</span>
              <span className="text-xs font-bold text-rose-400/80 num-ltr">
                {effectivePreviousPlan.stop_loss != null
                  ? `${effectivePreviousPlan.stop_loss.toFixed(2)} ج.م`
                  : "—"}
              </span>
            </div>
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">الهدف الأول السابق</span>
              <span className="text-xs font-bold text-gray-300 num-ltr">
                {effectivePreviousPlan.target_1 != null
                  ? `${effectivePreviousPlan.target_1.toFixed(2)} ج.م`
                  : "—"}
              </span>
            </div>
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">الهدف الثاني السابق</span>
              <span className="text-xs font-bold text-gray-300 num-ltr">
                {effectivePreviousPlan.target_2 != null
                  ? `${effectivePreviousPlan.target_2.toFixed(2)} ج.م`
                  : "—"}
              </span>
            </div>
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">الهدف الثالث السابق</span>
              <span className="text-xs font-bold text-gray-300 num-ltr">
                {effectivePreviousPlan.target_3 != null
                  ? `${effectivePreviousPlan.target_3.toFixed(2)} ج.م`
                  : "—"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Existing Position Details for Stock Owners */}
      {isOwner && (
        <div className="bg-surfaceHover/40 border border-surfaceBorder rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <Coins className="w-4 h-4 text-primary" />
              <span>تفاصيل المركز الحالي</span>
            </h3>
            {sharesOwnedNum > 0 && buyPriceNum > 0 && (
              <span
                className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                  isPositivePnL
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                }`}
              >
                {isPositivePnL ? "ربح غير محقق" : "خسارة غير محققة"}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-center">
            {/* عدد الأسهم المملوكة */}
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">عدد الأسهم المملوكة</span>
              <span className="text-base font-bold text-white num-ltr">
                {sharesOwnedNum > 0 ? `${sharesOwnedNum.toLocaleString()} سهم` : "—"}
              </span>
            </div>

            {/* متوسط سعر الشراء */}
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">متوسط سعر الشراء</span>
              <span className="text-base font-bold text-white num-ltr">
                {buyPriceNum > 0 ? `${buyPriceNum.toFixed(2)} ج.م` : "—"}
              </span>
            </div>

            {/* إجمالي تكلفة الشراء */}
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">إجمالي تكلفة الشراء</span>
              <span className="text-base font-bold text-white num-ltr">
                {costBasis > 0
                  ? `${costBasis.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ج.م`
                  : "—"}
              </span>
            </div>

            {/* القيمة الحالية للمركز */}
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">القيمة الحالية للمركز</span>
              <span className="text-base font-bold text-white num-ltr">
                {sharesOwnedNum > 0
                  ? `${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ج.م`
                  : "—"}
              </span>
            </div>

            {/* الربح / الخسارة الحالية */}
            <div
              className={`bg-surface border ${
                costBasis > 0
                  ? isPositivePnL
                    ? "border-emerald-500/30"
                    : "border-rose-500/30"
                  : "border-surfaceBorder"
              } rounded-lg p-2.5`}
            >
              <span className="text-[11px] text-gray-400 block mb-0.5">الربح / الخسارة الحالية</span>
              <span
                className={`text-base font-bold num-ltr ${
                  costBasis > 0
                    ? isPositivePnL
                      ? "text-emerald-400"
                      : "text-rose-400"
                    : "text-gray-400"
                }`}
              >
                {costBasis > 0
                  ? `${unrealizedPnL >= 0 ? "+" : ""}${unrealizedPnL.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })} ج.م`
                  : "—"}
              </span>
            </div>

            {/* نسبة الربح / الخسارة */}
            <div
              className={`bg-surface border ${
                costBasis > 0
                  ? isPositivePnL
                    ? "border-emerald-500/30"
                    : "border-rose-500/30"
                  : "border-surfaceBorder"
              } rounded-lg p-2.5`}
            >
              <span className="text-[11px] text-gray-400 block mb-0.5">نسبة الربح / الخسارة</span>
              <span
                className={`text-base font-bold num-ltr ${
                  costBasis > 0
                    ? isPositivePnL
                      ? "text-emerald-400"
                      : "text-rose-400"
                    : "text-gray-400"
                }`}
              >
                {costBasis > 0 ? `${unrealizedPnLPercent >= 0 ? "+" : ""}${unrealizedPnLPercent.toFixed(2)}%` : "—"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Position Sizing & Risk Management (For non-owners only) */}
      {!isOwner && position_sizing && (
        <div className="bg-surfaceHover/40 border border-surfaceBorder rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-warning" />
              <span>إدارة المخاطر وتحديد حجم الصفقة (Position Sizing)</span>
            </h3>
            <span className="text-[11px] text-gray-400">
              قاعدة المخاطرة: أقصى مخاطرة 1.5% | أقصى تخصيص 20%
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">عدد الأسهم المقترح</span>
              <span className="text-base font-bold text-primary num-ltr">
                {position_sizing.suggested_shares.toLocaleString()} سهم
              </span>
            </div>

            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">قيمة الصفقة الإجمالية</span>
              <span className="text-base font-bold text-white num-ltr">
                {position_sizing.position_value_egp.toLocaleString()} ج.م
              </span>
              <span className="text-[10px] text-gray-500 block">
                ({position_sizing.actual_allocation_pct}% من المحفظة)
              </span>
            </div>

            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">أقصى خسارة متوقعة</span>
              <span className="text-base font-bold text-rose-400 num-ltr">
                {position_sizing.max_expected_loss_egp.toLocaleString()} ج.م
              </span>
              <span className="text-[10px] text-gray-500 block">
                ({position_sizing.actual_risk_pct}% من رأس المال)
              </span>
            </div>

            <div className="bg-surface border border-surfaceBorder rounded-lg p-2.5">
              <span className="text-[11px] text-gray-400 block mb-0.5">رأس المال المعتمد</span>
              <span className="text-base font-bold text-white num-ltr">
                {position_sizing.capital.toLocaleString()} ج.م
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Multi-Factor Score Breakdown */}
      {trade_plan && trade_plan.factor_score != null && trade_plan.factor_breakdown && (
        <div className="border-t border-surfaceBorder pt-4 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 flex items-center gap-1.5 font-bold">
              <Percent className="w-4 h-4 text-accent" />
              <span>قوة التحليل الفني التراكمية:</span>
              <span className="text-white font-bold">{trade_plan.factor_score} / 100</span>
              {trade_plan.analysis_strength && (
                <span className="text-gray-500">({trade_plan.analysis_strength})</span>
              )}
            </span>
            <span className="text-[11px] text-gray-500">مؤشر إرشادي فقط ولا يمنح إشارة شراء بمفرده</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {Object.entries(trade_plan.factor_breakdown).map(([key, val]) => {
              const labels: Record<string, string> = {
                trend: "الاتجاه (Trend)",
                momentum: "الزخم (Momentum)",
                price_structure: "هيكل السعر (Structure)",
                liquidity_volatility: "السيولة والتقلب (Liquidity)",
              };
              return (
                <div key={key} className="bg-surfaceHover/50 border border-surfaceBorder rounded-lg p-2">
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-gray-400">{labels[key] || key}</span>
                    <span className="font-bold text-white">{val}/25</span>
                  </div>
                  <div className="w-full bg-surfaceBorder h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-primary h-full rounded-full transition-all duration-500"
                      style={{ width: `${(val / 25) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}