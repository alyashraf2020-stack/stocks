"use client";

import { useEffect, useState } from "react";
import { getStockCompany } from "@/lib/api";
import { CompanyProfile, CandleBar } from "@/lib/types";

const metrics: [string, string, string?][] = [
  ["price", "سعر المصدر", "ج.م"], ["change", "التغير", "ج.م"],
  ["change_percent", "نسبة التغير", "%"], ["open", "الافتتاح", "ج.م"],
  ["high", "أعلى سعر للجلسة", "ج.م"], ["low", "أقل سعر للجلسة", "ج.م"],
  ["volume", "حجم التداول"], ["average_volume", "متوسط حجم التداول"],
  ["week_52_high", "أعلى سعر خلال 52 أسبوعاً", "ج.م"],
  ["week_52_low", "أقل سعر خلال 52 أسبوعاً", "ج.م"],
  ["market_cap", "القيمة السوقية", "ج.م"], ["shares_outstanding", "عدد الأسهم"],
  ["revenue", "الإيرادات حسب المصدر", "ج.م"], ["eps", "ربحية السهم", "ج.م"],
  ["pe_ratio", "مضاعف الربحية"], ["dividend_per_share", "التوزيع للسهم حسب المصدر", "ج.م"],
  ["dividend_yield_percent", "عائد التوزيعات", "%"],
  ["one_year_return_percent", "التغير خلال سنة", "%"], ["beta", "معامل بيتا"],
];

function format(value: number | null | undefined, unit = "") {
  return value == null || !Number.isFinite(value) ? "غير متاح" :
    `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${unit}`;
}

export default function CompanyProfileCard({ ticker, refreshKey, latestBar }: {
  ticker: string; refreshKey: number; latestBar?: CandleBar;
}) {
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getStockCompany(ticker).then((value) => {
      if (active) setProfile(value);
    }).catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [ticker, refreshKey]);

  if (loading) return <div className="text-gray-400 text-sm p-4">جاري تحميل ملف الشركة والمؤشرات المالية...</div>;
  if (error || !profile) return <div className="text-amber-400 text-sm p-4">تعذر تحميل ملف الشركة. أعد المحاولة من زر تحديث البيانات.</div>;

  const indicators: [keyof CandleBar, string][] = [
    ["sma_20", "SMA 20"], ["sma_50", "SMA 50"], ["rsi_14", "RSI 14"],
    ["macd_line", "MACD"], ["macd_signal", "MACD Signal"],
    ["bb_upper", "Bollinger Upper"], ["bb_lower", "Bollinger Lower"], ["atr_14", "ATR 14"],
  ];
  return (
    <section className="space-y-5 bg-surface border border-surfaceBorder rounded-2xl p-5">
      <div className="space-y-2">
        <h2 className="text-lg font-bold text-white">ملف الشركة والمؤشرات المالية</h2>
        <p className="text-sm text-gray-300">{profile.description_ar}</p>
        <p className="text-xs text-gray-400">تاريخ القيد: {profile.listed_on || "غير متاح"} · العملة: الجنيه المصري</p>
      </div>
      <div className="text-xs text-gray-400 space-y-1">
        <p>مصدر الملخص: Investing.com · {profile.is_delayed === false ? "كما يعرضه المصدر" : profile.is_delayed === true ? "بيانات متأخرة" : "التأخير غير محدد"}</p>
        <p>وقت السعر لدى المصدر: {profile.quote_updated_at ? new Date(profile.quote_updated_at).toLocaleString("ar-EG", { timeZone: "Africa/Cairo" }) : "غير متاح"} (القاهرة)</p>
        <p>وقت جلب الملخص: {new Date(profile.fetched_at).toLocaleString("ar-EG", { timeZone: "Africa/Cairo" })} (القاهرة)</p>
        <p>الأرقام المالية كما يعرضها المصدر؛ الفترة المالية وتفاصيل التوزيعات متاحة عبر رابط القوائم المالية.</p>
        {profile.status !== "AVAILABLE" && <p className="text-amber-400">{profile.status === "UNAVAILABLE" ? "تعذر جلب ملخص الأسعار والمؤشرات المالية حالياً." : "بعض المؤشرات غير متاحة لدى المصدر."}</p>}
      </div>
      <dl className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {metrics.map(([key, label, unit]) => <div key={key} className="bg-surfaceHover rounded-xl p-3">
          <dt className="text-xs text-gray-400 mb-1">{label}</dt>
          <dd className="text-sm font-bold text-white num-ltr">{format(profile.metrics[key], unit)}</dd>
        </div>)}
      </dl>
      {latestBar && <div className="space-y-3">
        <h3 className="text-sm font-bold text-white">المؤشرات الفنية المحسوبة — جلسة {latestBar.session_date}</h3>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">{indicators.map(([key, label]) =>
          <div key={key} className="bg-surfaceHover rounded-xl p-3">
            <dt className="text-xs text-gray-400 mb-1">{label}</dt>
            <dd className="text-sm font-bold text-white num-ltr">{format(latestBar[key] as number | null | undefined)}</dd>
          </div>)}</dl>
      </div>}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-white">القوائم المالية والتوزيعات والأخبار — فتح المصدر</h3>
        <div className="flex flex-wrap gap-2">{profile.resources.map((link) =>
          <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-primary border border-surfaceBorder rounded-lg px-3 py-2 hover:bg-surfaceHover">{link.label} ↗</a>)}</div>
      </div>
    </section>
  );
}
