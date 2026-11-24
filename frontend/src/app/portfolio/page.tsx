"use client";

import ScannerNavigation from "@/components/ScannerNavigation";
import Link from "next/link";
import AIStockAnalysis from "@/components/AIStockAnalysis";
import { useEffect, useState } from "react";
import {
  dateLabel,
  errorMessage,
  freshnessLabel,
  numberLabel,
  Portfolio,
  thndr,
  toolLabels,
} from "@/lib/thndr";
export default function PortfolioPage() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    thndr<Portfolio>("portfolio", "GET", controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, []);
  async function sync() {
    setBusy(true);
    setError("");
    setData(null);
    try {
      setData(await thndr<Portfolio>("sync", "POST"));
    } catch (e) {
      setError(e instanceof Error ? e.message : errorMessage(""));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section dir="rtl" className="space-y-6">
      <header className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-3xl font-bold">محفظتي في ثاندر</h1>
      <ScannerNavigation />
          <p className="text-gray-400 mt-2">
            آخر مزامنة بتوقيت القاهرة · {dateLabel(data?.last_sync ?? null)}
          </p>
        </div>
        <div className="flex flex-wrap gap-3 items-center">
          <Link
            className="text-primary underline"
            href="/settings/integrations"
          >
            إدارة الربط
          </Link>
          <button
            className="rounded-lg bg-primary text-background px-4 py-2 font-bold disabled:opacity-40"
            disabled={busy}
            onClick={sync}
          >
            مزامنة المحفظة
          </button>
        </div>
      </header>
      {error && (
        <p role="alert" className="text-amber-300">
          {error}
        </p>
      )}
      {busy && <p role="status">جاري تحميل بيانات المحفظة…</p>}
      {data && !data.last_sync && (
        <p className="rounded-xl bg-surface border border-surfaceBorder p-5">
          اربط حسابك من إدارة الربط، وبعدها اختار مزامنة المحفظة.
        </p>
      )}
      {data?.last_sync && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {(
              [
                ["قيمة المحفظة", data.total_value],
                ["النقد المتاح", data.available_cash],
                ["المبلغ المستثمر", data.invested_amount],
                ["ربح وخسارة محققة", data.realized_pnl],
                ["ربح وخسارة غير محققة", data.unrealized_pnl],
              ] as const
            ).map(([label, value]) => (
              <div
                className="bg-surface border border-surfaceBorder rounded-xl p-4"
                key={label}
              >
                <p className="text-gray-400 text-sm mb-2">{label}</p>
                <p className="text-lg font-semibold">
                  {numberLabel(value)} {value !== null && "ج.م"}
                </p>
              </div>
            ))}
          </div>
          {data.account?.eligible_for_egx != null && (
            <p className="text-sm text-gray-300">
              أهلية الحساب للبورصة المصرية ·{" "}
              {data.account.eligible_for_egx ? "مؤهل" : "غير مؤهل"}
            </p>
          )}
          <h2 className="font-bold text-xl">المراكز الحالية</h2>
          {data.holdings === null ? (
            <p>بيانات المراكز غير متاحة.</p>
          ) : !data.holdings.length ? (
            <p>ثاندر رجّع قائمة مراكز فارغة.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {data.holdings.map((h, i) => {
                const q = h.quote,
                  price = q?.validation_status === "VALID" ? q.price : null;
                return (
                  <article
                    key={h.ticker + i}
                    className="rounded-xl border border-surfaceBorder bg-surface p-5"
                  >
                    <h3 className="text-xl font-bold text-primary">
                      {h.ticker}
                    </h3>
                    <dl className="grid grid-cols-2 gap-3 mt-4 text-sm">
                      {[
                        ["عدد الأسهم", numberLabel(h.quantity)],
                        ["متوسط الشراء (ج.م)", numberLabel(h.average_price)],
                        ["آخر سعر (ج.م)", numberLabel(price)],
                        [
                          "حالة السعر",
                          q ? freshnessLabel[q.freshness] : "غير متاح",
                        ],
                        [
                          "توقيت السعر",
                          q?.source_timestamp
                            ? dateLabel(q.source_timestamp)
                            : "غير متاح",
                        ],
                        [
                          "ربح وخسارة غير محققة (ج.م)",
                          numberLabel(h.unrealized_pnl),
                        ],
                      ].map(([title, val]) => (
                        <div key={title}>
                          <dt className="text-gray-400">{title}</dt>
                          <dd>{val}</dd>
                        </div>
                      ))}
                    </dl>
                  </article>
                );
              })}
            </div>
          )}
          {Object.keys(data.issues).length > 0 && (
            <details className="rounded-lg border border-surfaceBorder p-4">
              <summary>تفاصيل البيانات غير المتاحة</summary>
              <ul className="mt-3">
                {Object.entries(data.issues).map(([tool, code]) => (
                  <li key={tool}>
                    {toolLabels[tool] ?? tool} · {errorMessage(code)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <Link href="/risk" className="text-primary underline">تقييم مخاطر المحفظة</Link>
      <AIStockAnalysis portfolio />
    </section>
  );
}
