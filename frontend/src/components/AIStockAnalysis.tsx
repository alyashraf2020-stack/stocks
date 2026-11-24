"use client";

import { FormEvent, useState } from "react";
import { Analysis, aiLabels, aiRequest, signalLabels } from "@/lib/ai";
import { dateLabel, freshnessLabel, numberLabel } from "@/lib/thndr";

const inputClass =
  "block w-full rounded-lg border border-surfaceBorder bg-background mt-1 py-2 px-3";
const card =
  "rounded-xl border border-surfaceBorder bg-surface p-4 sm:p-5 space-y-3";

export function AnalysisCard({ analysis: a }: { analysis: Analysis }) {
  const metrics: [string, string][] = [
    ["السعر المرجعي (ج.م)", numberLabel(a.price)],
    ["حالة السعر", freshnessLabel[a.freshness]],
    [
      "المصدر",
      a.provider === "MANUAL_INPUT" ? "إدخال يدوي" : (a.provider ?? "غير متاح"),
    ],
    ["توقيت السعر", a.price_timestamp ? dateLabel(a.price_timestamp) : "غير متاح"],
    ["جلسة التحليل الفني", a.reference_session ?? "غير متاحة"],
    [
      "حالة الجلسة حسب الجدول",
      (
        {
          OPEN: "مفتوحة",
          CLOSED: "مغلقة",
          HALTED: "متوقفة",
          UNKNOWN: "غير مؤكدة",
        } as Record<string, string>
      )[a.market_status],
    ],
    [
      "التقييم الفني",
      (signalLabels[a.technical_rating ?? ""] ??
        a.technical_rating ??
        "غير متاح") + (a.score === null ? "" : " · " + numberLabel(a.score)),
    ],
    [
      "اتفاق المؤشرات",
      a.agreement_pct === null
        ? "غير متاح"
        : numberLabel(a.agreement_pct) + "%",
    ],
    [
      "التذبذب نسبةً للسعر",
      a.volatility_pct === null
        ? "غير متاح"
        : numberLabel(a.volatility_pct) + "%",
    ],
    ["حجم التداول النسبي", numberLabel(a.relative_volume)],
    [
      "المخاطرة الفنية",
      (
        {
          LOW: "منخفضة",
          MODERATE: "متوسطة",
          HIGH: "مرتفعة",
          UNKNOWN: "غير متاحة",
        } as Record<string, string>
      )[a.risk],
    ],
    ["حجم المركز المشروط (سهم)", numberLabel(a.suggested_shares)],
  ];
  if (a.levels) {
    metrics.push(
      [
        "نطاق الدخول (ج.م)",
        numberLabel(a.levels.lower) + " – " + numberLabel(a.levels.upper),
      ],
      ["وقف الخسارة (ج.م)", numberLabel(a.levels.stop)],
      ["الدعم (ج.م)", numberLabel(a.levels.support)],
      ["المقاومة (ج.م)", numberLabel(a.levels.resistance)],
      [
        "عائد إلى مخاطرة حسب الهدف",
        a.levels.reward_to_risk.map((v) => numberLabel(v)).join(" / "),
      ],
    );
    a.levels.targets.forEach((value, i) =>
      metrics.push(["الهدف " + (i + 1) + " (ج.م)", numberLabel(value)]),
    );
  }
  if (a.position)
    metrics.push(
      ["مصدر المركز", a.position.source === "THNDR" ? "ثاندر" : "إدخال يدوي"],
      ["عدد الأسهم", numberLabel(a.position.shares)],
      ["متوسط الشراء (ج.م)", numberLabel(a.position.average_price)],
      ["ربح أو خسارة تقديرية (ج.م)", numberLabel(a.position.unrealized_pnl)],
      [
        "التعرّض للمركز",
        a.position.exposure_pct === null
          ? "غير متاح"
          : numberLabel(a.position.exposure_pct) + "%",
      ],
      ["إدارة المركز", signalLabels[a.position.action]],
    );
  return (
    <article className={card}>
      <header className="flex flex-wrap justify-between items-center gap-2">
        <h2 className="font-bold text-lg">
          {a.company} <bdi className="text-primary">{a.ticker}</bdi>
        </h2>
        <span className="rounded-lg bg-primary/10 px-3 py-1 text-sm text-primary">
          {signalLabels[a.signal] ?? a.signal}
        </span>
      </header>
      <div>
        <h3 className="font-bold">القرار الحسابي</h3>
        <p className="text-gray-300">{a.explanation_ar}</p>
        <bdi className="text-xs text-gray-400">{a.decision}</bdi>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt className="text-gray-400">{label}</dt>
            <dd className="break-words">
              <bdi>{value}</bdi>
            </dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-gray-400">
        اتفاق المؤشرات يوضح اتجاه الإشارات الفنية. المستويات للمراجعة، وتحتاج
        سعرًا موثّقًا قبل اتخاذ أي إجراء.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {(
          [
            ["الأدلة الداعمة", a.supporting_ar],
            ["الأدلة المعارضة", a.opposing_ar],
            ["معلومات غير متاحة", a.missing_ar],
            ["شروط إلغاء الخطة", a.invalidation_ar],
            ["سيناريوهات إدارة المركز", a.position?.scenarios_ar ?? []],
          ] as const
        ).map(
          ([label, items]) =>
            items.length > 0 && (
              <div key={label}>
                <h3 className="font-bold mb-1">{label}</h3>
                <ul className="list-disc ps-5 text-sm text-gray-300">
                  {items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ),
        )}
      </div>
      {a.horizon_ar && (
        <p className="text-sm text-gray-300">
          {a.horizon_ar}{" "}
          {a.expires_at && <>راجع التحليل بعد {dateLabel(a.expires_at)}.</>}
        </p>
      )}
      {a.company_events.map((event) => (
        <a
          key={event.title_ar}
          href={event.source_url}
          className="block text-sm text-primary underline"
          target="_blank"
          rel="noreferrer"
        >
          {event.title_ar} · {event.event_date}
        </a>
      ))}
      <section className="rounded-lg border border-surfaceBorder p-3">
        <h3 className="font-bold">تفسير OpenAI</h3>
        <p className="text-sm text-gray-300 mt-1">
          {a.ai_explanation_ar ?? aiLabels[a.ai_status] ?? a.ai_status}
        </p>
        {a.usage && (
          <p className="text-xs text-gray-400 mt-2">
            تكلفة تقديرية{" "}
            <bdi>{a.usage.estimated_charge_usd.toFixed(6)} USD</bdi> ·{" "}
            {a.usage.input_tokens + a.usage.output_tokens} توكن حسب الرد
          </p>
        )}
      </section>
    </article>
  );
}

export default function AIStockAnalysis({
  ticker,
  portfolio = false,
}: {
  ticker?: string;
  portfolio?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<Analysis[] | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResults(null);
    const form = new FormData(event.currentTarget);
    const numeric = (name: string) =>
      form.get(name) ? Number(form.get(name)) : undefined;
    try {
      if (portfolio) {
        setResults(await aiRequest<Analysis[]>("portfolio", {}));
        return;
      }
      const shares = numeric("shares"),
        average = numeric("average");
      if ((shares === undefined) !== (average === undefined))
        throw new Error("اكتب عدد الأسهم ومتوسط الشراء مع بعض.");
      setResults([
        await aiRequest<Analysis>("analyze", {
          ticker: (ticker ?? String(form.get("ticker"))).trim().toUpperCase(),
          manual_price: numeric("price"),
          portfolio_value: numeric("capital"),
          cash: numeric("cash"),
          position:
            shares === undefined
              ? undefined
              : { shares, average_price: average },
        }),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل التحليل.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section dir="rtl" className="space-y-4">
      <form className={card} onSubmit={submit}>
        <h2 className="text-xl font-bold">
          {portfolio ? "تحليل مراكز ثاندر" : "تحليل السهم"}
        </h2>
        {!portfolio && (
          <>
            {!ticker && (
              <label className="block text-sm">
                رمز السهم
                <input
                  className={inputClass}
                  autoCapitalize="characters"
                  name="ticker"
                  dir="ltr"
                  maxLength={20}
                  required
                />
              </label>
            )}
            <details>
              <summary className="cursor-pointer text-primary">
                إدخال سعر أو مركز يدوي
              </summary>
              <div className="grid gap-3 mt-3 sm:grid-cols-2">
                {(
                  [
                    ["price", "السعر (ج.م)", "any", 0.01],
                    ["capital", "إجمالي المحفظة (ج.م)", "any", 0.01],
                    ["cash", "الكاش المتاح (ج.م)", "any", 0],
                    ["shares", "عدد الأسهم", 1, 1],
                    ["average", "متوسط الشراء (ج.م)", "any", 0.01],
                  ] as const
                ).map(([name, label, step, min]) => (
                  <label key={name} className="text-sm">
                    {label}
                    <input
                      className={inputClass}
                      dir="ltr"
                      type="number"
                      name={name}
                      min={min}
                      step={step}
                    />
                  </label>
                ))}
              </div>
            </details>
          </>
        )}
        <button
          disabled={busy}
          className="rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50"
        >
          {busy ? "جاري التحليل…" : portfolio ? "تحليل المحفظة" : "تحليل السهم"}
        </button>
        {error && (
          <p role="alert" className="text-amber-300">
            {error}
          </p>
        )}
      </form>
      {results?.length === 0 && (
        <p className={card}>
          اعمل مزامنة لمحفظة ثاندر عشان تظهر المراكز المتاحة للتحليل.
        </p>
      )}
      {results?.map((a) => (
        <AnalysisCard key={a.ticker} analysis={a} />
      ))}
    </section>
  );
}
