"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { display, simulationReason, strategies, Trade } from "@/lib/simulation";

export const panel = "space-y-4 rounded-xl border border-surfaceBorder bg-surface p-4";
export const field = "w-full rounded-lg border border-surfaceBorder bg-background p-2";
export const button = "rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50";
export const secondary = "rounded-lg border border-surfaceBorder px-4 py-2 text-primary disabled:opacity-50";

export function SimNav() {
  return <nav aria-label="المحاكاة" className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-primary">
    {[["/paper-trading", "المحفظة الافتراضية"], ["/paper-trading/accounts", "الحسابات"], ["/paper-trading/orders", "الأوامر"],
      ["/paper-trading/history", "السجل"], ["/backtesting", "الاختبار التاريخي"], ["/backtesting/results", "النتائج"]].map(([link, label]) =>
      <Link className="underline" href={link} key={link}>{label}</Link>)}
  </nav>;
}

export function Strategy({ name = "strategy", initial = "COMBINED", multiple = false }: {name?: string; initial?: string; multiple?: boolean}) {
  return <label className="grid gap-1 text-sm">الاستراتيجية
    <select name={name} defaultValue={multiple ? [initial] : initial} multiple={multiple} className={field}>
      {Object.entries(strategies).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
  </label>;
}

const costFields = [
  ["commission_rate", "عمولة الوسيط (%)"], ["charges_rate", "رسوم إضافية (%)"],
  ["buy_tax_rate", "ضريبة الشراء (%)"], ["sell_tax_rate", "ضريبة البيع (%)"],
  ["fixed_fee", "رسم ثابت للأمر (ج.م)"], ["minimum_commission", "حد أدنى للعمولة (ج.م)"],
  ["slippage_rate", "انزلاق السعر (%)"], ["spread_rate", "الفرق بين العرض والطلب (%)"],
  ["participation", "حد المشاركة في حجم الجلسة (%)"],
];
export function ExecutionForm() {
  return <fieldset className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <legend className="mb-2 font-semibold">افتراضات التنفيذ</legend>
    {costFields.map(([name, label]) => <label key={name} className="grid gap-1 text-sm">{label}
      <input required name={name} type="number" min={name === "participation" ? ".001" : "0"}
        max={name === "participation" ? "10" : undefined} step="any" className={field} />
    </label>)}
    <label className="grid gap-1 text-sm sm:col-span-2">مرجع الرسوم أو سبب الافتراضات
      <input name="assumptions_source" required minLength={3} maxLength={300} className={field} />
    </label>
    <p className="text-sm text-gray-400">التسوية بعد جلستين مؤهلتين. أدخل صفر صراحة لو القيمة صفر في السيناريو اللي بتختبره.</p>
  </fieldset>;
}
export function executionFrom(data: FormData) {
  return Object.fromEntries([...costFields.map(([key]) => [
    key, ["fixed_fee", "minimum_commission"].includes(key) ? String(data.get(key)) : Number(data.get(key)) / 100,
  ]), ["assumptions_source", String(data.get("assumptions_source"))]]);
}

export function Chart({ label, points, percent = false, comparison }: {
  label: string; points: (number | null)[]; percent?: boolean; comparison?: (number | null)[];
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    const observed = [...points, ...(comparison ?? [])].filter((x): x is number => x != null && Number.isFinite(x));
    if (!ctx || !observed.length) return;
    const [width, height] = [600, 170];
    const lower = Math.min(...observed), upper = Math.max(...observed);
    const range = upper - lower || 1;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#334155";
    for (const y of [12, 85, 158]) {
      ctx.beginPath(); ctx.moveTo(8, y); ctx.lineTo(width - 8, y); ctx.stroke();
    }
    function line(series: (number | null)[], color: string) {
      if (!ctx) return;
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      let joined = false;
      series.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) { joined = false; return; }
        const x = 8 + (width - 16) * index / Math.max(1, series.length - 1);
        const y = 158 - 146 * (value - lower) / range;
        if (joined) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        joined = true;
      });
      ctx.stroke();
    }
    if (comparison) line(comparison, "#fbbf24");
    line(points, "#34d399");
  }, [points, comparison]);
  const values = points.filter((p): p is number => p != null);
  return <figure className="space-y-1"><figcaption className="font-medium">{label}</figcaption>
    {values.length > 1
      ? <><canvas ref={canvas} width={600} height={170} className="w-full rounded border border-surfaceBorder" role="img" aria-label={label} />
        {comparison && <p className="text-sm"><span className="text-emerald-400">الاستراتيجية</span> · <span className="text-amber-300">المقارنة</span></p>}
        <p className="text-sm text-gray-400">أول قيمة {display(values[0], percent)} · آخر قيمة {display(values[values.length - 1], percent)}</p></>
      : <p className="text-sm text-gray-400">مفيش نقاط كفاية لعرض الرسم.</p>}
  </figure>;
}

export function Trades({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <p className="text-gray-400">مفيش تنفيذات افتراضية للعرض.</p>;
  return <div className="overflow-x-auto"><table className="w-full min-w-[660px] text-right text-sm">
    <thead><tr className="border-b border-surfaceBorder">{["الجلسة", "الرمز", "الجانب", "الكمية", "السعر", "الرسوم والضرايب", "المحقق", "السبب"].map((title) => <th className="p-2" key={title}>{title}</th>)}</tr></thead>
    <tbody>{trades.map((trade, index) => <tr className="border-b border-surfaceBorder" key={trade.order_id + index}>
      <td className="p-2"><bdi>{trade.trade_session}</bdi></td><td><bdi>{trade.ticker}</bdi></td>
      <td>{trade.side === "BUY" ? "شراء" : "بيع"}</td><td>{display(trade.shares)}</td><td>{display(trade.price)}</td>
      <td>{display(Number(trade.fees) + Number(trade.tax))}</td><td>{display(trade.realized)}</td>
      <td>{simulationReason[trade.reason] ?? trade.reason}{trade.scenario && <span className="block text-xs text-gray-400">{trade.scenario}</span>}</td>
    </tr>)}</tbody>
  </table></div>;
}
