"use client";

import { useEffect, useState } from "react";
import { AnalysisCard } from "@/components/AIStockAnalysis";
import { freshnessLabel, numberLabel } from "@/lib/thndr";
import { signalLabels } from "@/lib/ai";
import { reason, screenLabels } from "@/lib/risk";
import { categories, messages, Results, scannerRequest, scannerTime } from "@/lib/scanner";

const filters = [
  { key: "category", label: "الفئة", options: ["BUY_REVIEW", "ENTRY_WATCH", "BREAKOUT", "HOLDING_REVIEW", "RISK_BLOCKED", "SHARIA_BLOCKED", "UNAVAILABLE", "MONITOR"], names: categories },
  { key: "rating", label: "التقييم الفني", options: ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"], names: signalLabels },
  { key: "risk", label: "المخاطرة", options: ["LOW", "MODERATE", "HIGH", "UNKNOWN"], names: { LOW: "منخفضة", MODERATE: "متوسطة", HIGH: "مرتفعة", UNKNOWN: "غير معروفة" } },
  { key: "sharia", label: "الفحص الشرعي", options: Object.keys(screenLabels), names: screenLabels },
  { key: "freshness", label: "حداثة البيانات", options: Object.keys(freshnessLabel), names: freshnessLabel },
  { key: "signal", label: "القرار", options: ["STRONG_BUY", "BUY", "HOLD", "WAIT", "SELL", "STRONG_SELL", "NO_TRADE", "DATA_NOT_CURRENT", "INSUFFICIENT_DATA"], names: signalLabels },
];

export default function ScannerResults({ jobId, refresh = 0 }: { jobId?: number; refresh?: number }) {
  const [results, setResults] = useState<Results>();
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ ...choices, offset: String(offset), limit: "20", min_turnover: choices.min_turnover || "0" });
    if (jobId) query.set("job_id", String(jobId));
    scannerRequest<Results>("scanner/results?" + query).then((next) => {
      if (active) { setResults(next); setError(""); }
    }).catch((e: Error) => {
      if (active) { setResults(undefined); setError(e.message); }
    });
    return () => { active = false; };
  }, [choices, jobId, offset, refresh]);

  function filter(key: string, value: string) {
    setOffset(0);
    setChoices((current) => ({ ...current, [key]: value }));
  }

  return (
    <section className="space-y-4">
      <h2 className="text-xl font-bold">نتائج المتابعة الآلية</h2>
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {filters.map(({ key, label, options, names }) => (
          <label key={key} className="grid gap-1 text-sm">{label}
            <select className="rounded border border-surfaceBorder bg-surface p-2" value={choices[key] ?? ""} onChange={(e) => filter(key, e.target.value)}>
              <option value="">الكل</option>
              {options.map((option) => <option key={option} value={option}>{(names as Record<string, string>)[option] ?? option}</option>)}
            </select>
          </label>
        ))}
        <label className="grid gap-1 text-sm">القطاع
          <select className="rounded border border-surfaceBorder bg-surface p-2" value={choices.sector ?? ""} onChange={(e) => filter("sector", e.target.value)}>
            <option value="">الكل</option>
            {results?.sectors.map((sector) => <option key={sector}>{sector}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm">أقل سيولة تقديرية (ج.م)
          <input type="number" min={0} className="rounded border border-surfaceBorder bg-surface p-2" value={choices.min_turnover ?? ""} onChange={(e) => filter("min_turnover", e.target.value)} />
        </label>
      </div>
      {error && <p role="alert" className="text-amber-300">{error}</p>}
      {results?.error && <p role="alert" className="text-amber-300">{messages[results.error] ?? results.error}</p>}
      {results && !results.error && results.rows.length === 0 && <p className="text-gray-400">{results.job_id ? "مفيش نتائج مطابقة للفلاتر." : "مفيش جولة محفوظة للإعدادات الحالية."}</p>}
      {results?.rows.map((row) => (
        <details key={row.ticker} className="space-y-3 rounded-xl border border-surfaceBorder p-4">
          <summary className="cursor-pointer font-bold"><bdi>{row.ticker}</bdi> · {row.analysis?.company ?? ""} · {categories[row.category] ?? row.category}</summary>
          {row.reason && <p className="text-amber-300">{messages[row.reason] ?? reason(row.reason)}</p>}
          {row.rank !== null && <p className="text-sm">{row.qualified ? "تقييم المحفظة مكتمل وقت التحليل" : "ترتيب فني للمراجعة"} · {numberLabel(row.rank)} · {scannerTime(row.reviewed_at)}</p>}
          {row.observation?.time_basis === "SESSION_CLOSE" && <p className="text-sm text-gray-400">الوقت المرجعي لإغلاق الجلسة · {scannerTime(row.observation.source_timestamp)}</p>}
          {row.broker_observation && <p className="text-sm text-amber-300">رصد ثاندر · {numberLabel(row.broker_observation.price)} · {freshnessLabel[row.broker_observation.freshness]} · {scannerTime(row.broker_observation.source_timestamp)}</p>}
          {row.flags?.stop && <p className="text-amber-300">السعر المرجعي لمس مستوى الوقف المدخل أو نزل تحته.</p>}
          {Number(row.flags?.target) > 0 && <p className="text-sm">السعر المرجعي لمس هدف الخطة رقم {String(row.flags?.target)}.</p>}
          {row.analysis && <AnalysisCard analysis={row.analysis} />}
        </details>
      ))}
      {results && results.total > 20 && (
        <div className="flex gap-5 text-primary">
          <button disabled={offset === 0} className="underline disabled:opacity-40" onClick={() => setOffset(Math.max(0, offset - 20))}>السابق</button>
          <span className="text-gray-400">{Math.min(offset + 1, results.total)}–{Math.min(offset + 20, results.total)} من {results.total}</span>
          <button disabled={offset + 20 >= results.total} className="underline disabled:opacity-40" onClick={() => setOffset(offset + 20)}>التالي</button>
        </div>
      )}
    </section>
  );
}
