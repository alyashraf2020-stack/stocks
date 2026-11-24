"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import {
  formatRisk,
  ownerRequest,
  reason,
  ratiosAr,
  Screen,
  screenLabels,
} from "@/lib/risk";

type Overview = {
  method_url: string;
  index_url: string;
  islamic_mode: boolean;
  items: Screen[];
};
const input =
  "w-full mt-1 rounded-lg bg-background border border-surfaceBorder px-3 py-2";
const panel = "rounded-xl border border-surfaceBorder bg-surface p-4 space-y-3";
const metrics: [string, string, string][] = [
  ["reviewed_on", "تاريخ المراجعة", "date"],
  ["activity_source", "مصدر توثيق النشاط", "url"],
  ["period_end", "نهاية الفترة المحاسبية", "date"],
  ["financial_source", "رابط القوائم المالية", "url"],
  ["market_value_source", "مصدر متوسط القيمة السوقية خلال المراجعة", "url"],
  ["total_revenue", "إجمالي الإيرادات", "number"],
  ["noncompliant_income", "الإيرادات غير المتوافقة", "number"],
  ["total_assets", "إجمالي الأصول", "number"],
  ["average_market_value", "متوسط القيمة السوقية", "number"],
  ["interest_debt", "القروض بفائدة", "number"],
  ["interest_investments", "الاستثمارات بفائدة", "number"],
  ["liquid_assets", "الأصول السائلة", "number"],
  ["index_as_of", "تاريخ بيانات المؤشر", "date"],
  ["index_source", "رابط قائمة المؤشر", "url"],
];

export default function ShariaPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = async () => setData(await ownerRequest<Overview>("sharia"));
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const ticker = String(form.get("ticker")).trim().toUpperCase();
    const index = form.get("index");
    const evidence: Record<string, unknown> = {
      activity: form.get("activity"),
      ordinary_share: form.get("ordinary_share") ? form.get("ordinary_share") === "yes" : null,
      index_member: index ? index === "yes" : null,
    };
    for (const [key] of metrics)
      evidence[key] = String(form.get(key) ?? "").trim() || null;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const screened = await ownerRequest<Screen>(
        "sharia/" + encodeURIComponent(ticker),
        evidence,
      );
      await reload();
      setQuery(ticker);
      setFilter("");
      setNotice(screened.ticker + " · " + screenLabels[screened.status]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تسجيل الفحص.");
    } finally {
      setBusy(false);
    }
  }
  const results = (data?.items ?? []).filter(
    (row) =>
      (!filter || row.status === filter) &&
      (row.ticker.includes(query.toUpperCase()) ||
        row.company.includes(query) ||
        row.sector.includes(query)),
  );
  return (
    <section dir="rtl" className="mx-auto max-w-6xl space-y-5">
      <h1 className="text-3xl font-bold">الفحص الشرعي للأسهم</h1>
      <div className="flex flex-wrap gap-4 text-sm text-primary underline">
        <Link href="/risk">إعدادات الوضع الإسلامي</Link>
        {data && (
          <>
            <a href={data.method_url} target="_blank" rel="noreferrer">
              منهجية البورصة المصرية
            </a>
            <a href={data.index_url} target="_blank" rel="noreferrer">
              المكونات المنشورة للمؤشر
            </a>
          </>
        )}
      </div>
      {data && (
        <p className="text-gray-300 text-sm">
          {data.islamic_mode
            ? "الوضع الإسلامي شغّال. الشراء والتعزيز متاحين للمراجعة بعد اجتياز الفحص."
            : "الوضع الإسلامي متوقف. تقدر تراجع حالة أي سهم هنا."}
        </p>
      )}
      {error && (
        <p role="alert" className="text-amber-300">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-primary">
          <bdi>{notice}</bdi>
        </p>
      )}
      <details className={panel}>
        <summary className="font-bold cursor-pointer">
          تسجيل مراجعة من مصادر منشورة
        </summary>
        <form onSubmit={save} className="mt-3 space-y-3">
          <p className="text-sm text-gray-400">
            استخدم نفس العملة والوحدة في كل القيم المالية. سيب الحقل فاضي لو
            المعلومة غير متاحة.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="text-sm">
              رمز السهم
              <input
                className={input}
                name="ticker"
                dir="ltr"
                required
                maxLength={20}
              />
            </label>
            <label className="text-sm">
              النشاط الرئيسي
              <select className={input} name="activity" defaultValue="UNKNOWN">
                <option value="UNKNOWN">غير متحقق منه</option>
                <option value="PERMITTED">مستوفٍ</option>
                <option value="PROHIBITED">غير مستوفٍ</option>
              </select>
            </label>
            <label className="text-sm">
              نوع الورقة المالية
              <select className={input} name="ordinary_share">
                <option value="">غير متحقق منه</option>
                <option value="yes">سهم عادي</option>
                <option value="no">نوع آخر</option>
              </select>
            </label>
            {metrics.map(([name, label, type]) => (
              <label className="text-sm" key={name}>
                {label}
                <input
                  className={input}
                  name={name}
                  type={type}
                  dir="ltr"
                  required={["reviewed_on", "activity_source"].includes(name)}
                  min={type === "number" ? 0 : undefined}
                  step={type === "number" ? "any" : undefined}
                />
              </label>
            ))}
            <label className="text-sm">
              عضوية EGX33 حسب المصدر
              <select className={input} name="index">
                <option value="">غير متاحة</option>
                <option value="yes">مدرج</option>
                <option value="no">غير مدرج</option>
              </select>
            </label>
          </div>
          <button
            className="bg-primary text-background rounded-lg px-4 py-2 font-bold disabled:opacity-50"
            disabled={busy}
          >
            حفظ المراجعة
          </button>
        </form>
      </details>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          بحث بالرمز أو الشركة أو القطاع
          <input
            className={input}
            value={query}
            onChange={(e) => setQuery(e.target.value.trim())}
          />
        </label>
        <label className="text-sm">
          حالة الفحص
          <select
            className={input}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">الكل</option>
            {Object.entries(screenLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!data && !error && <p role="status">جاري تحميل الفحص…</p>}
      {data && results.length === 0 && <p>مفيش أسهم مطابقة.</p>}
      <div className="grid gap-2 md:grid-cols-2">
        {results.map((row) => (
          <details key={row.ticker} className={panel}>
            <summary className="cursor-pointer">
              <bdi className="text-primary font-semibold">{row.ticker}</bdi> ·{" "}
              {row.company} · {screenLabels[row.status]}
            </summary>
            <div className="mt-3 text-sm space-y-2">
              <p>{row.sector}</p>
              <ul className="list-disc ps-5">
                {row.reasons.map((code) => (
                  <li key={code}>{reason(code)}</li>
                ))}
              </ul>
              <dl className="grid grid-cols-2 gap-2">
                {Object.entries(row.limits).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-gray-400">{ratiosAr[key]}</dt>
                    <dd>
                      {formatRisk(row.ratios[key], true)} · الحد{" "}
                      {formatRisk(value, true)}
                    </dd>
                  </div>
                ))}
              </dl>
              {row.evidence && (
                <div className="space-y-1">
                  <p>
                    المراجعة <bdi>{row.evidence.reviewed_on}</bdi> · الفترة{" "}
                    <bdi>{row.evidence.period_end ?? "غير متاحة"}</bdi>
                  </p>
                  {row.evidence.index_member !== null && (
                    <p>
                      حسب قائمة <bdi>{row.evidence.index_as_of}</bdi> ·{" "}
                      {row.evidence.index_member
                        ? "مدرج في EGX33"
                        : "غير مدرج في EGX33"}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 text-primary underline">
                    {(
                      [
                        ["مصدر النشاط", row.evidence.activity_source],
                        ["القوائم المالية", row.evidence.financial_source],
                        [
                          "متوسط القيمة السوقية",
                          row.evidence.market_value_source,
                        ],
                        ["قائمة المؤشر", row.evidence.index_source],
                      ] as const
                    ).map(
                      ([label, url]) =>
                        url && (
                          <a
                            key={label}
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {label}
                          </a>
                        ),
                    )}
                  </div>
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
