"use client";

import { FormEvent, useEffect, useState } from "react";
import { button, Chart, executionFrom, ExecutionForm, field, panel, secondary, SimNav, Strategy, Trades } from "@/components/SimulationUI";
import { Dataset, display, Point, simulationReason, simulationRequest, simulationStatus, strategies, Trade } from "@/lib/simulation";

type Account = {id: string; name: string; capital: string; automated: boolean; archived: boolean; strategy: string};
type Portfolio = Account & {
  settled_cash: number; available_cash: number; reserved_cash: number; unsettled_cash: number;
  equity: number | null; invested_cost: number; realized: number; unrealized: number | null;
  fees: number; taxes: number; daily_return: number | null; total_return: number | null; gross_exposure: number | null;
  cursor: string | null; failure: string | null; history: Point[]; tickers: string[]; datasets: string[];
  positions: {ticker: string; shares: number; settled: number; average_cost: number; mark: number | null; stop: number; target: number}[];
};
type Order = {id: string; status: string; filled: number; mandatory: boolean; reason: string | null;
  request: {ticker: string; shares: number; side: string; kind: string}};
type History = {trades: Trade[]; ledger: {id: number; kind: string; created: number; data: Record<string, unknown>}[]};
const presets = [5000, 10000, 20000, 50000];
const kinds: Record<string, string> = { MARKET: "سوق", LIMIT: "أمر محدد", STOP: "وقف", TARGET: "هدف" };

export default function PaperDashboard({ page }: {page: "portfolio" | "accounts" | "orders" | "history"}) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [id, setId] = useState("");
  const [portfolio, setPortfolio] = useState<Portfolio>();
  const [orders, setOrders] = useState<Order[]>([]);
  const [history, setHistory] = useState<History>();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [reload, setReload] = useState(0);
  const [side, setSide] = useState("BUY");
  const [kind, setKind] = useState("MARKET");
  const [position, setPosition] = useState("");
  const path = "paper-trading/accounts";

  useEffect(() => {
    let alive = true;
    Promise.all([simulationRequest<Account[]>(path), simulationRequest<{approved: Dataset[]}>("backtesting/datasets")])
      .then(([data, catalog]) => {
        if (!alive) return;
        setAccounts(data); setDatasets(catalog.approved.filter((d) => d.kind === "EQUITY"));
        setId((current) => {
          const selected = current || window.localStorage.getItem("egx-paper-account") || "";
          return data.some((a) => a.id === selected) ? selected : data[0]?.id ?? "";
        });
      }).catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [reload]);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setPortfolio(undefined); setOrders([]); setHistory(undefined);
    const route = path + "/" + id;
    Promise.all([
      simulationRequest<Portfolio>(route),
      page === "orders" ? simulationRequest<Order[]>(route + "/orders") : Promise.resolve([]),
      page === "history" ? simulationRequest<History>(route + "/history") : Promise.resolve(undefined),
    ]).then(([p, o, h]) => { if (alive) { setPortfolio(p); setOrders(o); setHistory(h); } })
      .catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [id, page, reload]);

  function selectAccount(next: string) {
    setId(next); window.localStorage.setItem("egx-paper-account", next); setError("");
  }
  async function action(run: () => Promise<void>, success: string) {
    setWorking(true); setError(""); setNotice("");
    try { await run(); setNotice(success); setReload((x) => x + 1); }
    catch (e) { setError((e as Error).message); }
    finally { setWorking(false); }
  }
  function newAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action(async () => {
      const item = await simulationRequest<{id: string}>(path, {
        key: crypto.randomUUID(), name: String(data.get("name")).trim(), capital: Number(data.get("capital")),
        strategy: data.get("strategy"), execution: executionFrom(data), datasets: data.getAll("datasets"),
      });
      selectAccount(item.id);
    }, "اتعمل الحساب الافتراضي.");
  }
  function order(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const amount = (name: string) => data.get(name) ? String(data.get(name)) : null;
    void action(async () => {
      const result = await simulationRequest<Order>(path + "/" + id + "/orders", {
        key: crypto.randomUUID(), ticker: data.get("ticker"), side, kind, shares: Number(data.get("shares")),
        limit: amount("limit"), trigger: amount("trigger"), stop: amount("stop"), target: amount("target"),
      });
      if (result.status === "REJECTED") throw new Error(simulationReason[result.reason ?? ""] ?? result.reason ?? "الأمر مرفوض");
    }, "اتسجّل الأمر الافتراضي للجلسة المؤهلة.");
  }
  const curve = portfolio?.history.map((point) => point.equity == null ? null : Number(point.equity)) ?? [];
  let peak = 0;
  const drawdown = portfolio?.history.map((point) => {
    if (point.nav == null) return null;
    const value = Number(point.nav);
    peak = Math.max(peak, value);
    return peak > 0 ? (peak - value) / peak : null;
  }) ?? [];

  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">{({ portfolio: "المحفظة الافتراضية", accounts: "حسابات التداول الافتراضي", orders: "الأوامر الافتراضية", history: "سجل التداول الافتراضي" })[page]}</h1>
    <SimNav />
    <p className="text-sm text-amber-300">كل الأرصدة والأوامر والتنفيذات في الصفحة دي افتراضية بالجنيه المصري.</p>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {accounts.length > 0 && <label className="grid max-w-md gap-1 text-sm">الحساب الافتراضي
      <select value={id} onChange={(e) => selectAccount(e.target.value)} className={field}>
        {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.archived ? " · مؤرشف" : ""}</option>)}
      </select></label>}
    {page === "accounts" && <form className={panel} onSubmit={newAccount}>
      <h2 className="text-xl font-bold">حساب افتراضي جديد</h2>
      {!datasets.length && <p className="text-amber-300">استورد حزمة أسعار معتمدة من صفحة الاختبار التاريخي الأول.</p>}
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="grid gap-1 text-sm">اسم الحساب<input name="name" required maxLength={60} className={field}/></label>
        <label className="grid gap-1 text-sm">رأس المال (ج.م)<input name="capital" type="number" min={1} max={100000000} defaultValue={10000} list="paper-capitals" required className={field}/>
          <datalist id="paper-capitals">{presets.map((p) => <option key={p} value={p}/>)}</datalist></label>
        <Strategy />
      </div>
      <label className="grid max-w-xl gap-1 text-sm">حزم أسعار الأسهم
        <select name="datasets" multiple required className={field}>{datasets.map((d) => <option key={d.id} value={d.id}>{d.ticker} · {d.source} · {d.last_session}</option>)}</select>
      </label>
      <ExecutionForm />
      <button disabled={working || !datasets.length} className={button}>إنشاء حساب افتراضي</button>
    </form>}
    {portfolio && (page === "portfolio" || page === "accounts") && <div className={panel}>
      <h2 className="text-xl font-bold">{portfolio.name} · {strategies[portfolio.strategy]}</h2>
      {portfolio.failure && <p className="text-amber-300">{simulationReason[portfolio.failure] ?? portfolio.failure}</p>}
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">{[
        ["رأس المال الأولي", portfolio.capital], ["قيمة المحفظة", portfolio.equity], ["سيولة متاحة", portfolio.available_cash],
        ["رصيد مسوّى", portfolio.settled_cash], ["محجوز", portfolio.reserved_cash], ["لسه تحت التسوية", portfolio.unsettled_cash],
        ["تكلفة المراكز", portfolio.invested_cost], ["ربح/خسارة محققة", portfolio.realized], ["ربح/خسارة غير محققة", portfolio.unrealized],
        ["رسوم وضرائب", Number(portfolio.fees) + Number(portfolio.taxes)], ["العائد اليومي", portfolio.daily_return, true],
        ["العائد المعدّل للتدفقات", portfolio.total_return, true], ["التعرّض للسوق", portfolio.gross_exposure, true],
      ].map(([label, value, pct]) => <div key={String(label)}><dt className="text-sm text-gray-400">{label}</dt><dd>{display(value as string | number | null, Boolean(pct))}</dd></div>)}</dl>
      <p className="text-sm text-gray-400">آخر جلسة تمت مراجعتها {portfolio.cursor ?? "غير متاحة"}</p>
      {!portfolio.archived && <form key={id + portfolio.strategy + portfolio.datasets.join()} className="space-y-3" onSubmit={(e) => {
        e.preventDefault(); const data = new FormData(e.currentTarget);
        void action(async () => { await simulationRequest(path + "/" + id + "/settings", {
          strategy: data.get("strategy"), automated: data.has("automated"), datasets: data.getAll("datasets"),
        }); }, "اتحفظت الإعدادات.");
      }}>
        <div className="grid gap-3 sm:grid-cols-2"><Strategy initial={portfolio.strategy}/>
        <label className="grid gap-1 text-sm">الحزم المستخدمة
          <select multiple name="datasets" required defaultValue={portfolio.datasets} className={field}>{datasets.map((d) =>
            <option key={d.id} value={d.id}>{d.ticker} · {d.source} · {d.last_session}</option>)}</select>
        </label></div>
        <label className="flex gap-2 text-sm"><input name="automated" type="checkbox" defaultChecked={portfolio.automated}/> تفعيل الأوامر الافتراضية الآلية</label>
        <button className={secondary} disabled={working}>حفظ الإعدادات</button>
      </form>}
      {page === "accounts" && !portfolio.archived && <>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => {
          e.preventDefault(); const data = new FormData(e.currentTarget);
          void action(async () => { await simulationRequest(path + "/" + id + "/cash", {
            key: crypto.randomUUID(), kind: data.get("kind"), amount: data.get("amount"),
          }); }, "اتسجّلت الحركة الافتراضية.");
        }}>
          <label className="grid gap-1 text-sm">حركة الرصيد<select name="kind" className={field}><option value="DEPOSIT">إيداع افتراضي</option><option value="WITHDRAWAL">سحب افتراضي</option></select></label>
          <label className="grid gap-1 text-sm">المبلغ<input name="amount" required type="number" step="any" min=".000001" className={field}/></label>
          <button className={secondary} disabled={working}>تسجيل الحركة</button>
        </form>
        <button className="text-amber-300 underline" disabled={working} onClick={() => {
          if (window.confirm("أرشفة الحساب هتوقفه وتلغي الأوامر المعلّقة. تأكد إنك عايز تكمل.")) void action(async () => {
            await simulationRequest(path + "/" + id + "/archive", {});
          }, "اتأرشف الحساب.");
        }}>أرشفة الحساب</button>
      </>}
      {page === "portfolio" && <>
        <div className="grid gap-4 md:grid-cols-2"><Chart label="قيمة المحفظة الافتراضية" points={curve}/><Chart label="التراجع من القمة" points={drawdown} percent/></div>
        <h3 className="font-semibold">المراكز الافتراضية</h3>
        {portfolio.positions.map((p) => <p key={p.ticker} className="text-sm"><bdi>{p.ticker}</bdi> · {display(p.shares)} سهم ({display(p.settled)} مسوّى) · متوسط التكلفة {display(p.average_cost)} · آخر تقييم {display(p.mark)} · وقف {display(p.stop)} · هدف {display(p.target)}</p>)}
        {!portfolio.positions.length && <p className="text-sm text-gray-400">مفيش مراكز مفتوحة.</p>}
      </>}
    </div>}
    {portfolio && page === "orders" && <>
      {!portfolio.archived && <form className={panel} onSubmit={order}>
        <h2 className="font-semibold">أمر افتراضي جديد</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 text-sm">السهم<select required name="ticker" value={position} onChange={(e) => setPosition(e.target.value)} className={field}>
            <option value="">اختار سهم</option>{portfolio.tickers.map((t) => <option key={t}>{t}</option>)}</select></label>
          <label className="grid gap-1 text-sm">الجانب<select value={side} onChange={(e) => {setSide(e.target.value);setKind("MARKET");}} className={field}><option value="BUY">شراء</option><option value="SELL">بيع</option></select></label>
          <label className="grid gap-1 text-sm">النوع<select value={kind} onChange={(e) => setKind(e.target.value)} className={field}>{Object.entries(kinds).filter(([k]) => side === "SELL" || k === "MARKET" || k === "LIMIT").map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
          <label className="grid gap-1 text-sm">الكمية<input name="shares" type="number" min={1} required className={field}/></label>
          {kind === "LIMIT" && <label className="grid gap-1 text-sm">السعر المحدد<input name="limit" type="number" min=".000001" step="any" required className={field}/></label>}
          {(kind === "STOP" || kind === "TARGET") && <label className="grid gap-1 text-sm">سعر التفعيل<input name="trigger" type="number" min=".000001" step="any" required className={field}/></label>}
          {side === "BUY" && [["stop", "وقف الحماية"], ["target", "سعر الهدف"]].map(([key, label]) =>
            <label key={key} className="grid gap-1 text-sm">{label}<input name={key} type="number" min=".000001" step="any" required className={field}/></label>)}
        </div>
        <button className={button} disabled={working}>تسجيل الأمر الافتراضي</button>
      </form>}
      <div className={panel}><h2 className="font-semibold">الأوامر</h2>
        {orders.map((o) => <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surfaceBorder pb-2 text-sm" key={o.id}>
          <span><bdi>{o.request.ticker}</bdi> · {o.request.side === "BUY" ? "شراء" : "بيع"} · {kinds[o.request.kind]} · {o.filled}/{o.request.shares} · {simulationStatus[o.status]} {o.reason && (" · " + (simulationReason[o.reason] ?? o.reason))}</span>
          {!portfolio.archived && !o.mandatory && ["PENDING", "ACCEPTED", "PARTIALLY_FILLED"].includes(o.status) &&
            <button className="text-primary underline" disabled={working} onClick={() => void action(async () => {
              await simulationRequest(path + "/" + id + "/orders/" + o.id + "/cancel", {});
            }, "اتلغى الأمر الافتراضي.")}>إلغاء</button>}
        </div>)}
      </div>
    </>}
    {history && <div className={panel}>
      <Trades trades={history.trades}/>
      <a className="text-primary underline" href={"/api/v1/" + path + "/" + id + "/history/export.json"} download="virtual-history.json">تصدير السجل JSON</a>
      <details><summary className="cursor-pointer font-medium">دفتر الحركات الافتراضية</summary>
        <ul className="mt-2 space-y-1 text-sm">{history.ledger.map((entry) => <li key={entry.id}>
          #{entry.id} · {entry.kind} · {new Date(entry.created * 1000).toLocaleString("ar-EG", {timeZone: "Africa/Cairo"})}
          {entry.data.amount != null && (" · " + display(String(entry.data.amount)))}</li>)}</ul>
      </details>
    </div>}
    {!accounts.length && page !== "accounts" && <p className="text-gray-400">مفيش حساب افتراضي. ابدأ من صفحة الحسابات.</p>}
  </section>;
}
