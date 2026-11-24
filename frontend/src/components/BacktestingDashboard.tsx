"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { button, Chart, ExecutionForm, executionFrom, field, panel, secondary, SimNav, Strategy, Trades } from "@/components/SimulationUI";
import { Dataset, display, Point, Run, simulationReason, simulationRequest, simulationStatus, strategies, Trade } from "@/lib/simulation";

type Catalog = {approved: Dataset[]; cached_inventory: {ticker: string; provider: string; rows: number; first: string; last: string}[]};
type Scenario = {
  scenario: string; strategy: string; start: string; end: string; curve: Point[];
  metrics: Record<string, unknown> & {drawdown_curve: {day: string; drawdown: number | null}[]; monthly: {month: string; return: number | null; sessions: number}[]};
  coverage: Record<string, {bars_available: number; warmup_ready: number; expected: number}>;
  diagnostics: Record<string, number>;
  benchmarks: {cash_return: number; approved: {ticker: string; kind?: string; return?: number; reason?: string; series?: {day: string; return: number}[]} | null;
    buy_hold: Record<string, {return?: number; reason?: string}>};
  execution: Record<string, unknown>;
};
type Result = Run & {result: null | {
  availability: string; profitability?: string; limitation?: string; islamic_limitation?: string;
  excluded: Record<string, string>; scenarios: Scenario[];
  configuration: {datasets: Record<string, {source: string; digest: string; basis: string}>; methodology: Record<string, string>; risk: Record<string, unknown>};
}};
const metrics: [string, string, boolean?][] = [
  ["starting_capital", "رأس المال"], ["ending_equity", "القيمة النهائية"],
  ["net_profit", "صافي الربح أو الخسارة"], ["total_return", "العائد الصافي", true],
  ["annualized_return", "العائد السنوي", true], ["max_drawdown", "أكبر تراجع", true],
  ["drawdown_duration", "مدة التراجع (جلسات)"], ["trades", "تنفيذات الخروج المكتملة"],
  ["gross_profit", "مجموع المكاسب المحققة"], ["gross_loss", "مجموع الخسائر المحققة"],
  ["profit_factor", "معامل الربح"], ["win_rate", "نسبة التنفيذات الرابحة", true], ["loss_rate", "نسبة الخاسرة", true],
  ["expectancy", "متوسط المحقق لكل خروج"], ["average_win", "متوسط المكسب"], ["average_loss", "متوسط الخسارة"],
  ["average_holding_days", "متوسط مدة الاحتفاظ"], ["sharpe", "Sharpe"], ["sortino", "Sortino"],
  ["commissions", "العمولات"], ["fees", "إجمالي الرسوم"], ["taxes", "الضرائب"], ["slippage", "الانزلاق التقديري"],
  ["turnover", "دوران المحفظة"], ["market_exposure", "جلسات التعرّض", true],
];
const windows: Record<string, string> = {
  FULL: "الفترة الكاملة", IN_SAMPLE: "الفترة الأولى", OUT_OF_SAMPLE: "خارج العينة",
  COST_UP_50: "ضغط تكاليف 1.5×", COST_DOUBLE: "ضغط تكاليف 2×",
};

export function BacktestSetup() {
  const [catalog, setCatalog] = useState<Catalog>();
  const [id, setId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    simulationRequest<Catalog>("backtesting/datasets").then(setCatalog).catch((e: Error) => setError(e.message));
  }, [refresh]);

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setId("");
    try {
      const rawRisk = String(form.get("risk") ?? "").trim();
      const islamic = form.has("islamic");
      let risk: Record<string, unknown> | null = rawRisk ? JSON.parse(rawRisk) : null;
      if (islamic && !risk) risk = await simulationRequest("risk/settings");
      if (islamic && risk) risk = { ...risk, islamic_mode: true };
      const job = await simulationRequest<{id: string}>("backtesting/runs", {
        tickers: String(form.get("tickers") ?? "").toUpperCase().split(/[\s,،]+/).filter(Boolean),
        datasets: form.getAll("datasets"), watchlist: form.has("watchlist"), strategies: form.getAll("strategies"),
        start: form.get("start"), end: form.get("end"), capital: form.get("capital"),
        execution: executionFrom(form), benchmark: form.get("benchmark") || null, robustness: form.get("robustness"),
        risk, seed: Number(form.get("seed")),
      });
      setId(job.id);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = new FormData(event.currentTarget).get("dataset");
    if (!(file instanceof File) || !file.size || file.size > 2_000_000) {
      setError("اختار ملف JSON صالح حجمه أقل من 2 ميجابايت."); return;
    }
    setBusy(true); setError("");
    try {
      await simulationRequest("backtesting/datasets", JSON.parse(await file.text()));
      setRefresh((n) => n + 1);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">الاختبار التاريخي</h1><SimNav/>
    <p className="text-sm text-gray-400">اختبار افتراضي على جلسات مكتملة. التنفيذ يبدأ من جلسة لاحقة وبيحسب حدود السعر والحجم والتسوية.</p>
    {error && <p className="text-amber-300" role="alert">{error}</p>}
    {id && <Link className="text-primary underline" href={"/backtesting/results/" + id}>الجولة اتضافت للطابور. تابع النتيجة</Link>}
    <form className={panel} onSubmit={start}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="grid gap-1 text-sm">رموز الأسهم<input name="tickers" placeholder="COMI, ABUK" className={field} dir="ltr"/></label>
        <label className="grid gap-1 text-sm">أول جلسة<input required type="date" name="start" className={field}/></label>
        <label className="grid gap-1 text-sm">آخر جلسة<input required type="date" name="end" className={field}/></label>
        <label className="grid gap-1 text-sm">رأس المال الافتراضي<input type="number" name="capital" required defaultValue={10000} min={1} className={field}/></label>
        <Strategy name="strategies" multiple />
        <label className="grid gap-1 text-sm">حزم أسعار محددة
          <select multiple name="datasets" className={field}>{catalog?.approved.filter((d) => d.kind === "EQUITY").map((d) => <option key={d.id} value={d.id}>{d.ticker} · {d.source} · {d.last_session}</option>)}</select>
        </label>
        <label className="grid gap-1 text-sm">المؤشر المرجعي
          <select name="benchmark" className={field}><option value="">النقد والاحتفاظ بالسهم</option>{catalog?.approved.filter((d) => d.kind !== "EQUITY").map((d) => <option key={d.id} value={d.id}>{d.ticker} · {d.kind}</option>)}</select>
        </label>
        <label className="grid gap-1 text-sm">اختبار المتانة<select name="robustness" className={field}>
          <option value="NONE">الفترة كاملة</option><option value="SPLIT">تقسيم زمني 70/30</option>
          <option value="WALK_FORWARD">نوافذ متتابعة</option><option value="STRESS">ضغط الرسوم والسيولة</option>
        </select></label>
        <label className="grid gap-1 text-sm">بذرة الإعادة<input type="number" name="seed" defaultValue={42} min={0} max={4294967295} className={field}/></label>
      </div>
      <div className="flex flex-wrap gap-4 text-sm"><label className="flex gap-2"><input name="watchlist" type="checkbox"/> أضف قائمة المتابعة المحفوظة</label>
        <label className="flex gap-2"><input name="islamic" type="checkbox"/> اشترط الفحص الشرعي المتاح وقت القرار</label></div>
      <details><summary className="cursor-pointer">سياسة المخاطر الخاصة بالاختبار</summary>
        <label className="block text-sm text-gray-400">اتركها فاضية لاستخدام السياسة المحفوظة، أو أدخل كائن RiskPolicy من واجهة API.
          <textarea name="risk" dir="ltr" rows={4} className={field}/></label>
      </details>
      <ExecutionForm/>
      <button className={button} disabled={busy}>إضافة الاختبار للطابور</button>
    </form>
    <form className={panel} onSubmit={upload}>
      <h2 className="text-xl font-bold">استيراد بيانات تاريخية مصرّح باستخدامها</h2>
      <p className="text-sm text-gray-400">صيغة DatasetUpload موثّقة في OpenAPI. الحزمة بتثبت هوية السهم وتقويم الجلسات ومواعيد الإتاحة وإجراءات الشركة.</p>
      <input name="dataset" required type="file" accept=".json,application/json" className={field}/>
      <button className={secondary} disabled={busy}>تحقق واحفظ الحزمة</button>
    </form>
    <details className={panel}><summary className="cursor-pointer font-semibold">تغطية الكاش المحلي الأولية</summary>
      <p className="text-sm text-gray-400">الأعداد خام؛ أهلية التنفيذ محتاجة حزمة معتمدة.</p>
      {catalog?.cached_inventory.map((item) => <div key={item.ticker + item.provider} className="text-sm">
        <bdi>{item.ticker}</bdi> · {item.provider} · {item.rows} صف · {item.first} إلى {item.last}</div>)}
    </details>
  </section>;
}

export function BacktestList() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    simulationRequest<Run[]>("backtesting/runs").then(setRuns).catch((e: Error) => setError(e.message));
  }, []);
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">جولات الاختبار التاريخي</h1><SimNav/>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {runs.map((run) => <Link key={run.id} href={"/backtesting/results/" + run.id} className={"block " + panel}>
      <p className="text-primary">{run.strategies.map((s) => strategies[s]).join("، ")}</p>
      <p className="text-sm"><bdi>{run.start}</bdi> إلى <bdi>{run.end}</bdi> · {simulationStatus[run.status]} · {run.progress}%</p>
    </Link>)}
    {!runs.length && !error && <p className="text-gray-400">مفيش جولات محفوظة.</p>}
  </section>;
}

export function BacktestDetail({ id }: {id: string}) {
  const [run, setRun] = useState<Result>();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const path = "backtesting/runs/" + id;
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const outcome = await simulationRequest<Result>(path);
        if (alive) setRun(outcome);
        if (outcome.status === "SUCCEEDED") {
          const records = await simulationRequest<Trade[]>(path + "/trades?limit=500");
          if (alive) setTrades(records);
        }
      } catch (e) { if (alive) setError((e as Error).message); }
    };
    void load();
    const interval = window.setInterval(load, 3500);
    return () => {alive = false; window.clearInterval(interval);};
  }, [path]);
  const result = run?.result;
  const scenario = result?.scenarios[selected];
  const benchmark = scenario?.benchmarks.approved;
  const selectedTrades = scenario && trades.filter((item) => item.scenario === scenario.strategy + ":" + scenario.scenario);

  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">نتيجة الاختبار التاريخي</h1><SimNav/>
    {error && <p className="text-amber-300" role="alert">{error}</p>}
    {run && <div className={panel}>
      <p>{simulationStatus[run.status]} · {run.progress}% · <bdi>{run.start}</bdi> إلى <bdi>{run.end}</bdi></p>
      {(run.status === "RUNNING" || run.status === "PENDING") && <button className={secondary} onClick={async () => {
        try { await simulationRequest(path + "/cancel", {}); } catch (e) { setError((e as Error).message); }
      }}>إلغاء الجولة</button>}
      {run.error && <p className="text-amber-300">{simulationReason[run.error] ?? run.error}</p>}
      {result && <>
        <p className="text-amber-300">الربحية لسه غير متحققة. النتائج تخص الفترة والأسهم والافتراضات المختارة.</p>
        {result.availability !== "ANALYZED" && <p className="text-amber-300">{simulationReason[result.availability] ?? result.availability}</p>}
        {result.islamic_limitation && <p className="text-amber-300">{simulationReason[result.islamic_limitation]}</p>}
        {Object.entries(result.excluded).map(([ticker, code]) => <p key={ticker}><bdi>{ticker}</bdi> · {simulationReason[code] ?? code}</p>)}
        <div className="flex flex-wrap gap-4 text-primary">
          <a href={"/api/v1/" + path + "/export.csv"} className="underline">تصدير التنفيذات CSV</a>
          <a href={"/api/v1/" + path} download="egx-backtest.json" className="underline">تصدير التقرير JSON</a>
        </div>
      </>}
    </div>}
    {!!result?.scenarios.length && <label className="grid max-w-md gap-2 text-sm">السيناريو
      <select className={field} value={selected} onChange={(e) => setSelected(Number(e.target.value))}>
        {result.scenarios.map((s, index) => <option value={index} key={s.strategy + s.scenario}>{strategies[s.strategy]} · {windows[s.scenario] ?? s.scenario}</option>)}
      </select></label>}
    {scenario && <div className={panel}>
      <p className="text-sm text-gray-400"><bdi>{scenario.start}</bdi> إلى <bdi>{scenario.end}</bdi> · العينة من الأسهم المختارة وقد تستبعد أسهم خرجت من السوق.</p>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {metrics.map(([key, label, percentage]) => <div key={key}><dt className="text-sm text-gray-400">{label}</dt>
          <dd>{display(scenario.metrics[key] as number | null, percentage)}</dd></div>)}
      </dl>
      <div className="grid gap-4 md:grid-cols-2">
        <Chart label="قيمة المحفظة الافتراضية" points={scenario.curve.map((p) => p.equity == null ? null : Number(p.equity))}/>
        <Chart label="التراجع من القمة" points={scenario.metrics.drawdown_curve.map((p) => p.drawdown)} percent/>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="space-y-2"><h2 className="font-semibold">المقارنة المرجعية</h2>
          <p>النقد · {display(scenario.benchmarks.cash_return, true)}</p>
          <Chart label="الاستراتيجية مقابل المرجع" percent points={scenario.curve.map((point) =>
            point.equity == null ? null : Number(point.equity) / Number(scenario.metrics.starting_capital) - 1)}
            comparison={benchmark?.series?.map((point) => point.return) ?? scenario.curve.map(() => 0)} />
          {benchmark && <p><bdi>{benchmark.ticker}</bdi> · {benchmark.reason ? simulationReason[benchmark.reason] : display(benchmark.return, true)} · {benchmark.kind}</p>}
          {Object.entries(scenario.benchmarks.buy_hold).map(([ticker, record]) => <p className="text-sm" key={ticker}>
            الاحتفاظ السعري · <bdi>{ticker}</bdi> · {record.reason ? simulationReason[record.reason] ?? record.reason : display(record.return, true)}</p>)}
        </section>
        <section className="space-y-2"><h2 className="font-semibold">الأداء الشهري</h2>
          {scenario.metrics.monthly.map((month) => <p className="text-sm" key={month.month}><bdi>{month.month}</bdi> · {display(month.return, true)} · {month.sessions} جلسة</p>)}
        </section>
      </div>
      <section className="space-y-2"><h2 className="font-semibold">تغطية البيانات</h2>
        {Object.entries(scenario.coverage).map(([ticker, coverage]) => <p key={ticker} className="text-sm"><bdi>{ticker}</bdi> · {coverage.bars_available}/{coverage.expected} جلسة · {coverage.warmup_ready} جاهزة للمؤشرات</p>)}
        {Object.entries(scenario.diagnostics).map(([reason, count]) => <p key={reason} className="text-sm text-gray-400">{simulationReason[reason] ?? reason} · {count}</p>)}
      </section>
      <details><summary className="cursor-pointer font-semibold">المصادر، المخاطر، وافتراضات التنفيذ</summary>
        <pre dir="ltr" className="mt-2 max-h-96 overflow-auto rounded border border-surfaceBorder p-3 text-xs">{JSON.stringify({datasets: result?.configuration.datasets, methodology: result?.configuration.methodology, risk: result?.configuration.risk, execution: scenario.execution}, null, 2)}</pre>
      </details>
      <section className="space-y-2">
        <h2 className="font-semibold">توزيع تنفيذات الخروج</h2>
        {(["wins", "losses", "flat"] as const).map((key) => <div key={key} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-2 text-sm">
          <span>{({wins: "رابحة", losses: "خاسرة", flat: "تعادل"})[key]}</span>
          <meter className="w-full" min={0} max={Math.max(1, Number(scenario.metrics.trades))} value={Number(scenario.metrics[key] ?? 0)} aria-label={key}/>
          <span>{display(Number(scenario.metrics[key] ?? 0))}</span>
        </div>)}
      </section>
      <h2 className="font-semibold">التنفيذات الافتراضية</h2><Trades trades={selectedTrades || []}/>
    </div>}
  </section>;
}
