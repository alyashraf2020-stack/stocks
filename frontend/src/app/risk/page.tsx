"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import ScannerNavigation from "@/components/ScannerNavigation";
import { ScannerSettings, scannerRequest } from "@/lib/scanner";
import { formatRisk, Numeric, ownerRequest, Policy, reason } from "@/lib/risk";

type Metrics = Record<string, Numeric>;
type Review = {
  portfolio: Metrics & {
    source: string;
    missing: string[];
    stock_breaches: string[];
    sector_breaches: string[];
    stop_breaches: string[];
    stock_concentration: Metrics;
    sector_concentration: Metrics;
  };
  sizing: (Metrics & { blockers: string[] }) | null;
  scenario: (Metrics & { limitations: string[] }) | null;
};
const panel = "rounded-xl border border-surfaceBorder bg-surface p-4 space-y-4";
const input =
  "w-full rounded-lg bg-background border border-surfaceBorder mt-1 py-2 px-3";
const primary =
  "rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50";
const fields: [string, string, boolean][] = [
  ["max_trade_risk", "مخاطرة الصفقة", true],
  ["max_stock_allocation", "تخصيص السهم", true],
  ["max_total_exposure", "إجمالي التعرض", true],
  ["max_sector_exposure", "تخصيص القطاع", true],
  ["max_daily_loss", "خسارة اليوم", true],
  ["max_drawdown", "تراجع المحفظة", true],
  ["max_open_positions", "عدد المراكز المفتوحة", false],
  ["max_aggregate_risk", "المخاطر المجمّعة", true],
  ["min_reward_to_risk", "أقل عائد إلى مخاطرة بعد التكاليف", false],
  ["min_daily_turnover", "أقل سيولة تقديرية يومية (ج.م)", false],
  ["commission_rate", "العمولة لكل جانب", true],
  ["buy_tax_rate", "ضريبة الشراء", true],
  ["sell_tax_rate", "ضريبة البيع", true],
  ["slippage_rate", "الانزلاق المقدر", true],
  ["stop_gap_rate", "فجوة الوقف المقدرة", true],
  ["max_snapshot_minutes", "أقصى عمر للبيانات (دقيقة)", false],
];
const actions: Record<string, string> = {
  HOLD: "احتفاظ",
  WAIT: "انتظار",
  ADD_TO_POSITION: "زيادة المركز",
  PARTIAL_SELL: "تخفيف جزئي",
  FULL_EXIT: "خروج كامل",
  MOVE_STOP_LOSS: "رفع الوقف",
  TAKE_PARTIAL_PROFIT: "جني ربح جزئي",
};
const splitRows = (value: FormDataEntryValue | null) =>
  String(value ?? "")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => line.split(",").map((x) => x.trim() || null));
const raw = (form: FormData, key: string) =>
  String(form.get(key) ?? "").trim() || null;

function MetricsView({
  items,
  values,
}: {
  items: [string, string, boolean?][];
  values: Metrics;
}) {
  return (
    <dl className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map(([key, label, pct]) => (
        <div key={key}>
          <dt className="text-sm text-gray-400">{label}</dt>
          <dd className="font-semibold">{formatRisk(values[key], pct)}</dd>
        </div>
      ))}
    </dl>
  );
}
function Reasons({ codes }: { codes: string[] }) {
  return codes.length ? (
    <ul className="text-sm text-amber-300 list-disc ps-6">
      {codes.map((code, i) => (
        <li key={code + i}>{reason(code)}</li>
      ))}
    </ul>
  ) : null;
}

export default function RiskPage() {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [source, setSource] = useState("MANUAL");
  const [result, setResult] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    ownerRequest<Policy>("risk/settings")
      .then(setPolicy)
      .catch((e) => setError(e.message));
  }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next: Record<string, unknown> = {};
    for (const field of ["advanced_enabled", "islamic_mode", "kill_switch"])
      next[field] = form.has(field);
    for (const [key, , pct] of fields) {
      const value = raw(form, key);
      next[key] =
        value === null ? null : pct ? Number(value) / 100 : Number(value);
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setPolicy(await ownerRequest<Policy>("risk/settings", next));
      setResult(null);
      setNotice("اتحفظت سياسة المحفظة.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }
  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    const time = raw(f, "as_of"),
      ticker = raw(f, "scenario_ticker"),
      quantity = raw(f, "scenario_shares");
    if (time && !Number.isFinite(new Date(time).getTime())) {
      setError("راجع توقيت المحفظة.");
      return;
    }
    const request = {
      source,
      candidate_ticker: raw(f, "ticker")?.toUpperCase() ?? null,
      scenario: ticker
        ? {
            ticker: ticker.toUpperCase(),
            action: raw(f, "action"),
            shares: quantity === null ? null : Number(quantity),
            revised_stop: raw(f, "revised_stop"),
          }
        : null,
      ...(source === "MANUAL"
        ? {
            manual: {
              as_of: time ? new Date(time).toISOString() : null,
              equity: raw(f, "equity"),
              settled_cash: raw(f, "settled_cash"),
              buying_power: raw(f, "buying_power"),
              adjusted_equity_now: raw(f, "adjusted_equity_now"),
              positions: f.has("positions_complete")
                ? splitRows(f.get("positions")).map(
                    ([
                      ticker,
                      shares,
                      mark,
                      average_cost,
                      stop,
                      sellable_shares,
                    ]) => ({
                      ticker: ticker?.toUpperCase(),
                      shares,
                      mark,
                      average_cost,
                      stop,
                      sellable_shares,
                    }),
                  )
                : null,
              pending_buys: f.has("pending_complete")
                ? splitRows(f.get("pending")).map(
                    ([ticker, notional, reserved_cash, planned_risk]) => ({
                      ticker: ticker?.toUpperCase(),
                      notional,
                      reserved_cash,
                      planned_risk,
                    }),
                  )
                : null,
              adjusted_history: splitRows(f.get("history")).map(
                ([day, equity]) => ({ day, equity }),
              ),
            },
          }
        : {}),
    };
    setBusy(true);
    setResult(null);
    setError("");
    try {
      const button = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
      if (button?.value === "scanner" && request.manual) {
        const settings = await scannerRequest<ScannerSettings>("scanner/settings");
        await scannerRequest("scanner/settings", { ...settings, manual: request.manual });
        setNotice("اتحفظت لقطة المحفظة اليدوية. اختار وضع المحفظة اليدوية من إعدادات الماسح.");
      } else {
        setResult(await ownerRequest<Review>("risk/review", request));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حساب المخاطر.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="max-w-6xl mx-auto space-y-5" dir="rtl">
      <h1 className="text-3xl font-bold">مخاطر المحفظة</h1>
      <ScannerNavigation />
      <Link className="text-primary underline" href="/sharia">
        الفحص الشرعي للأسهم
      </Link>
      {error && (
        <p role="alert" className="text-amber-300">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-primary">
          {notice}
        </p>
      )}
      {policy && (
        <form className={panel} onSubmit={save}>
          <h2 className="text-xl font-bold">سياسة المحفظة</h2>
          <div className="flex flex-wrap gap-4">
            {(
              [
                ["advanced_enabled", "تطبيق الحدود المتقدمة على التحليل"],
                ["islamic_mode", "الوضع الإسلامي"],
                ["kill_switch", "إيقاف الشراء والتعزيز"],
              ] as const
            ).map(([key, label]) => (
              <label className="flex gap-2 items-center" key={key}>
                <input
                  type="checkbox"
                  name={key}
                  defaultChecked={policy[key]}
                />
                {label}
              </label>
            ))}
          </div>
          <details>
            <summary className="cursor-pointer text-primary">
              الحدود والرسوم
            </summary>
            <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
              {fields.map(([key, label, pct]) => {
                const v = policy[key];
                return (
                  <label className="text-sm" key={key}>
                    {label}
                    {pct && " (%)"}
                    <input
                      name={key}
                      type="number"
                      min="0"
                      step="any"
                      className={input}
                      dir="ltr"
                      defaultValue={
                        v == null
                          ? ""
                          : pct
                            ? Number((Number(v) * 100).toFixed(8))
                            : String(v)
                      }
                    />
                  </label>
                );
              })}
            </div>
          </details>
          <button disabled={busy} className={primary}>
            حفظ السياسة
          </button>
        </form>
      )}
      <form className={panel} onSubmit={review}>
        <h2 className="text-xl font-bold">تحليل المحفظة</h2>
        <label className="block">
          مصدر البيانات
          <select
            className={input}
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setResult(null);
            }}
          >
            <option value="MANUAL">إدخال يدوي</option>
            <option value="THNDR">ثاندر · آخر مزامنة مصرح بها</option>
          </select>
        </label>
        {source === "MANUAL" && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(
                [
                  ["as_of", "توقيت بيانات المحفظة", "datetime-local"],
                  ["equity", "إجمالي قيمة المحفظة (ج.م)", "number"],
                  ["settled_cash", "الكاش المسوّى قبل الحجز (ج.م)", "number"],
                  ["buying_power", "القوة الشرائية الصافية (ج.م)", "number"],
                  [
                    "adjusted_equity_now",
                    "القيمة الحالية بعد استبعاد الإيداعات والسحوبات",
                    "number",
                  ],
                ] as const
              ).map(([name, label, type]) => (
                <label className="text-sm" key={name}>
                  {label}
                  <input
                    className={input}
                    name={name}
                    type={type}
                    min={type === "number" ? 0 : undefined}
                    step={type === "number" ? "any" : undefined}
                    dir="ltr"
                  />
                </label>
              ))}
            </div>
            <details>
              <summary className="text-primary cursor-pointer">
                المراكز والأوامر والتقييمات السابقة
              </summary>
              <div className="space-y-3 mt-3 text-sm">
                <label className="block">
                  <input type="checkbox" name="positions_complete" /> قائمة
                  المراكز كاملة، حتى لو فاضية
                </label>
                <label className="block">
                  كل مركز في سطر · الرمز، العدد، السعر، متوسط الشراء، الوقف،
                  الأسهم المتاحة للبيع
                  <textarea
                    className={input}
                    dir="ltr"
                    name="positions"
                    rows={3}
                    placeholder="TICKER,shares,mark,cost,stop,sellable"
                  />
                </label>
                <label className="block">
                  <input type="checkbox" name="pending_complete" /> قائمة أوامر
                  الشراء المعلقة كاملة، حتى لو فاضية
                </label>
                <label className="block">
                  كل أمر في سطر · الرمز، قيمة الأمر، الكاش المحجوز، المخاطرة
                  المخططة
                  <textarea
                    className={input}
                    dir="ltr"
                    name="pending"
                    rows={2}
                    placeholder="TICKER,notional,reserved,risk"
                  />
                </label>
                <label className="block">
                  كل إغلاق في سطر · التاريخ وقيمة المحفظة بعد استبعاد الإيداعات
                  والسحوبات
                  <textarea
                    className={input}
                    dir="ltr"
                    name="history"
                    rows={3}
                    placeholder="YYYY-MM-DD,equity"
                  />
                </label>
              </div>
            </details>
          </>
        )}
        <details>
          <summary className="text-primary cursor-pointer">
            حجم صفقة مشروطة أو إدارة مركز
          </summary>
          <div className="grid gap-3 mt-3 sm:grid-cols-2">
            <label>
              رمز السهم لحساب الحجم
              <input className={input} name="ticker" dir="ltr" maxLength={20} />
            </label>
            <label>
              رمز المركز
              <input
                className={input}
                name="scenario_ticker"
                dir="ltr"
                maxLength={20}
              />
            </label>
            <label>
              السيناريو
              <select className={input} name="action">
                {Object.entries(actions).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              كمية البيع الجزئي
              <input
                className={input}
                type="number"
                name="scenario_shares"
                min="1"
              />
            </label>
            <label>
              الوقف المعدّل (ج.م)
              <input
                className={input}
                type="number"
                name="revised_stop"
                min=".01"
                step="any"
              />
            </label>
          </div>
        </details>
        <button disabled={busy} className={primary}>
          {busy ? "جاري التقييم…" : "احسب المخاطر"}
        </button>
        {source === "MANUAL" && <button type="submit" value="scanner" disabled={busy} className="text-primary underline disabled:opacity-50">حفظ لقطة المحفظة اليدوية للماسح</button>}
      </form>
      {result && (
        <article className={panel}>
          <h2 className="text-xl font-bold">
            تقييم{" "}
            {result.portfolio.source === "THNDR"
              ? "محفظة ثاندر"
              : "المحفظة اليدوية"}
          </h2>
          <MetricsView
            values={result.portfolio}
            items={[
              ["total_exposure", "التعرّض (ج.م)"],
              ["total_exposure_ratio", "نسبة التعرّض", true],
              ["cash_ratio", "نسبة الكاش المسوّى", true],
              ["available_cash", "المتاح بعد الحجز"],
              ["reserved_cash", "الكاش المحجوز"],
              ["reported_buying_power", "القوة الشرائية المعلنة"],
              ["aggregate_position_risk", "المخاطرة المخططة للمراكز"],
              ["available_risk_budget", "ميزانية المخاطرة المتبقية"],
              ["daily_loss_ratio", "خسارة اليوم", true],
              ["drawdown_ratio", "التراجع", true],
              ["position_count", "عدد المراكز"],
              ["sector_count", "عدد القطاعات"],
              ["largest_stock_ratio", "أكبر تخصيص لسهم", true],
            ]}
          />
          <Reasons codes={result.portfolio.missing} />
          {result.portfolio.stock_breaches.length > 0 && (
            <p>أسهم فوق الحد · {result.portfolio.stock_breaches.join("، ")}</p>
          )}
          {result.portfolio.sector_breaches.length > 0 && (
            <p>
              قطاعات فوق الحد · {result.portfolio.sector_breaches.join("، ")}
            </p>
          )}
          {result.portfolio.stop_breaches.length > 0 && (
            <p>
              مراكز عند الوقف أو تحته ·{" "}
              {result.portfolio.stop_breaches.join("، ")}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ["توزيع الأسهم", result.portfolio.stock_concentration],
              ["توزيع القطاعات", result.portfolio.sector_concentration],
            ].map(([title, values]) => (
              <div key={String(title)}>
                <h3 className="font-semibold">{String(title)}</h3>
                {Object.entries(values as Metrics).map(([key, value]) => (
                  <p key={key} className="text-sm">
                    <bdi>{key}</bdi> · {formatRisk(value, true)}
                  </p>
                ))}
              </div>
            ))}
          </div>
          {result.sizing && (
            <section className="space-y-2">
              <h3 className="font-semibold">حجم الصفقة المشروط</h3>
              <MetricsView
                values={result.sizing}
                items={[
                  ["shares", "عدد الأسهم"],
                  ["estimated_fees", "تكاليف الشراء"],
                  ["planned_risk", "مخاطرة الوقف المخططة"],
                  ["cash_after", "المتبقي من الكاش"],
                  ["reward_to_risk", "العائد إلى المخاطرة بعد التكاليف"],
                ]}
              />
              <Reasons codes={result.sizing.blockers} />
            </section>
          )}
          {result.scenario && (
            <section className="space-y-2">
              <h3 className="font-semibold">نتيجة سيناريو المركز</h3>
              <MetricsView
                values={result.scenario}
                items={[
                  ["current_value", "القيمة"],
                  ["average_cost", "متوسط الشراء"],
                  ["unrealized_pnl", "الربح أو الخسارة غير المحققة"],
                  ["unrealized_return", "العائد غير المحقق", true],
                  ["exposure_ratio", "التعرّض", true],
                  ["remaining_allocation", "التخصيص المتاح"],
                  ["risk_before", "المخاطرة قبل"],
                  ["risk_after", "المخاطرة بعد"],
                  ["estimated_fees", "الرسوم"],
                  ["revised_average_cost", "المتوسط المعدّل"],
                  ["remaining_cash", "الكاش المتبقي"],
                  ["unsettled_proceeds", "متحصلات غير مسوّاة"],
                ]}
              />
              <Reasons codes={result.scenario.limitations} />
            </section>
          )}
          <p className="text-sm text-gray-400">
            حساب الوقف تقديري. الفجوات والتنفيذ الفعلي ممكن يخلّوا الخسارة أكبر
            من الحساب.
          </p>
        </article>
      )}
    </section>
  );
}
