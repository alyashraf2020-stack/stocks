"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnalysisCard } from "@/components/AIStockAnalysis";
import { aiRequest, Opportunity } from "@/lib/ai";
import { numberLabel } from "@/lib/thndr";

const components: Record<string, string> = {
  technical: "القوة الفنية",
  trend: "الاتجاه",
  liquidity_proxy: "سيولة تقديرية",
  reward_to_risk: "العائد إلى المخاطرة",
  entry_proximity: "القرب من الدخول",
  freshness: "حداثة بيانات الجلسة",
  existing_exposure: "تعرّض المحفظة",
  missing_fundamentals: "البيانات المالية الناقصة",
};

export default function OpportunitiesPage() {
  const [rows, setRows] = useState<Opportunity[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  async function load(includePortfolio: boolean) {
    setBusy(true);
    setError("");
    try {
      setRows(
        await aiRequest<Opportunity[]>(
          "opportunities" + (includePortfolio ? "?include_portfolio=true" : ""),
        ),
      );
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : "تعذّر تحميل الفرص.");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load(false);
  }, []);
  return (
    <section dir="rtl" className="space-y-4">
      <h1 className="text-3xl font-bold">الفرص للمراجعة</h1>
      <p className="text-sm text-gray-400">
        ترتيب حسابي مبني على آخر جلسة مكتملة وخطط الدخول المتاحة.
      </p>
      <div className="flex flex-wrap gap-4 text-primary">
        <Link href="/ai-trading" className="underline">
          تحليل سهم
        </Link>
        <button
          className="underline disabled:opacity-50"
          disabled={busy}
          onClick={() => load(true)}
        >
          احتسب التعرّض من ثاندر
        </button>
      </div>
      {busy && <p role="status">جاري حساب الفرص…</p>}
      {error && (
        <p role="alert" className="text-amber-300">
          {error}
        </p>
      )}
      {!busy && !error && !rows.length && (
        <p>البيانات الحالية لا تحتوي على خطط صالحة للترتيب.</p>
      )}
      {rows.map((row) => (
        <details
          key={row.ticker}
          className="rounded-xl border border-surfaceBorder p-4 space-y-3"
        >
          <summary className="cursor-pointer font-bold">
            <bdi>{row.ticker}</bdi> · {row.company} · {numberLabel(row.score)}
          </summary>
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {Object.entries(row.components).map(([key, value]) => (
              <div key={key}>
                <dt className="text-gray-400">{components[key]}</dt>
                <dd>
                  {key === "existing_exposure" && !row.exposure_known
                    ? "غير متاح"
                    : numberLabel(value)}
                </dd>
              </div>
            ))}
          </dl>
          <AnalysisCard analysis={row.analysis} />
        </details>
      ))}
    </section>
  );
}
