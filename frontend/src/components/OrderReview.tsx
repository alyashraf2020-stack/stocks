"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { numberLabel, ops, opsButton, opsField, opsOutline, opsPanel, timeLabel } from "@/lib/operations";
import { activeStates, checks, intents, modeLabels, orderLabel } from "@/lib/orderReview";

type Money = string | number | null;
type Check = {code: string; status: string; evidence: string; action: string; checked_at: string; mandatory: boolean};
type Readiness = {status: string; broker_handoff: boolean; checks: Check[];
  capabilities: {connection: string; scopes: string[]; granted_reads: string[]; documented: Record<string,string>; official_schema_verified: boolean}};
type Draft = {
  id: string; state: string; ticker: string; company: string; isin: string; exchange: string; currency: string;
  intent: string; side: string; source: string; version: number; order_type: string; reference: Money; limit: Money;
  requested_limit?: Money; held: Money; sellable: Money; buying_power: Money; cash_after: Money; requested_shares: number | null; shares: number | null;
  costs: {value: Money; commission: Money; tax: Money; required_cash: Money};
  freshness: string; provider?: string; observation_at?: string; reference_session?: string;
  entry_zone: [number,number] | null; stop: Money; targets: number[] | null; risk: Money; reward_to_risk: Money;
  before_exposure: Money; after_exposure: Money; sharia: string; supporting: string[]; opposing: string[];
  explanation: string; ai_explanation: string | null; scenario_blockers: string[]; origin: string;
  created: number; expires: number; fingerprint: string; handoff_enabled: boolean; readiness?: Readiness;
  broker: {submission: string; proposal_status: string; execution_status: string};
  broker_quote: {price: Money; freshness: string; observation_at?: string} | null;
};
type Event = {kind: string; created: number; previous?: string; reason?: string};
type Settings = {mode: string; automatic_drafts: boolean; max_quote_age: number; max_adverse_move_bps: number; revision: number};
const link = "inline-flex min-h-11 items-center font-semibold text-primary underline";
const sources: Record<string, string> = {ANALYSIS: "تحليل السوق", MANUAL: "لقطة يدوية", THNDR: "لقطة ثاندر المصرّح بها"};
const official = "https://www.thndr.app/";

function Navigation() {
  return <nav className="flex flex-wrap gap-4 text-sm" aria-label="مراجعة الأوامر">
    <Link className={link} href="/orders">الأوامر</Link><Link className={link} href="/orders/proposals">المسودات</Link>
    <Link className={link} href="/orders/history">السجل</Link><Link className={link} href="/trading-readiness">الجاهزية</Link>
    <Link className={link} href="/settings/trading">إعدادات التداول</Link>
  </nav>;
}

function CheckList({report}: {report: Readiness}) {
  return <div className="space-y-3">
    <p className="rounded-xl border border-amber-400/30 p-3 font-semibold text-amber-300">الإرسال الرسمي محجوب. راجع الأدلة والإجراءات المطلوبة تحت.</p>
    {report.checks.map((check) => <article key={check.code} className={opsPanel}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">{checks[check.code] ?? check.code}</h3>
        <span className={check.status === "PASS" ? "text-emerald-300" : "text-amber-300"}>{orderLabel(check.status)}</span>
      </div>
      <p className="text-sm">{check.action}</p>
      <p className="break-words text-sm text-gray-400">الدليل <bdi>{orderLabel(check.evidence)}</bdi> · اتراجع {timeLabel(check.checked_at)}</p>
    </article>)}
  </div>;
}

export function ReadinessPage() {
  const [result, setResult] = useState<Readiness>();
  const [error, setError] = useState("");
  useEffect(() => {ops<Readiness>("trading-readiness").then(setResult).catch((why: Error) => setError(why.message));}, []);
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">جاهزية التداول</h1><Navigation/>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {!result && !error && <p role="status">جاري فحص الأدلة…</p>}
    {result && <>
      <article className={opsPanel}><h2 className="font-bold">صلاحيات ثاندر</h2>
        <p>{orderLabel(result.capabilities.connection)} · <bdi>{result.capabilities.scopes.join("، ") || "مفيش صلاحيات متحققة"}</bdi></p>
        <p className="break-words text-sm text-gray-400">أدوات القراءة الممنوحة <bdi>{result.capabilities.granted_reads.join("، ") || "غير متاح"}</bdi></p>
      </article>
      <CheckList report={result}/>
    </>}
  </section>;
}

export function TradingControl() {
  const [settings, setSettings] = useState<Settings>();
  const [policy, setPolicy] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([ops<Settings>("orders/settings"), ops<Record<string, unknown>>("risk/settings")])
      .then(([values, risk]) => {setSettings(values);setPolicy(risk);}).catch((why: Error) => setError(why.message));
  }, []);
  function patch(data: Partial<Settings>) {setSettings((old) => old ? {...old, ...data} : old);}
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true);setError("");setNote("");
    try {setSettings(await ops<Settings>("orders/settings", settings));setNote("الإعدادات اتحفظت.");}
    catch (why) {setError((why as Error).message);}
    finally {setBusy(false);}
  }
  async function stop() {
    if (!policy) return;
    setBusy(true);setError("");setNote("");
    try {
      const current = await ops<Record<string, unknown>>("risk/settings");
      setPolicy(await ops<Record<string, unknown>>("risk/settings", {...current, kill_switch: true}));
      setNote("الإيقاف الطارئ اتفعّل. مسودات الشراء غير المرسلة فقدت صلاحيتها.");
    } catch (why) {setError((why as Error).message);}
    finally {setBusy(false);}
  }
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">إعدادات التداول</h1><Navigation/>
    {error && <p role="alert" className="text-amber-300">{error}</p>}{note && <p role="status">{note}</p>}
    {settings && <form className={opsPanel} onSubmit={save}>
      <label className="block max-w-md">وضع التشغيل<select className={opsField} value={settings.mode}
        onChange={(e) => patch({mode: e.target.value, automatic_drafts: e.target.value === "SEMI_AUTOMATIC_REVIEW" && settings.automatic_drafts})}>
        {Object.entries(modeLabels).map(([key, title]) => <option value={key} key={key}>{title}</option>)}</select></label>
      <label className="flex min-h-11 items-center gap-2"><input type="checkbox" disabled={settings.mode !== "SEMI_AUTOMATIC_REVIEW"}
        checked={settings.automatic_drafts} onChange={(e) => patch({automatic_drafts: e.target.checked})}/> أنشئ مسودات من الماسح للمراجعة</label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>الحد الأقصى لعمر السعر · ثانية<input className={opsField} type="number" min={5} max={60} value={settings.max_quote_age} onChange={(e) => patch({max_quote_age: Number(e.target.value)})}/></label>
        <label>حد تغير السعر ضد الصفقة · نقطة أساس<input className={opsField} type="number" min={0} max={100} value={settings.max_adverse_move_bps} onChange={(e) => patch({max_adverse_move_bps: Number(e.target.value)})}/></label>
      </div>
      <p className="text-sm text-gray-400">أوضاع التشغيل بتحدد المراجعة داخل التطبيق. التنفيذ الافتراضي منفصل والإرسال الرسمي محجوب.</p>
      <button className={opsButton} disabled={busy}>حفظ</button>
    </form>}
    <article className={opsPanel}><h2 className="font-bold">الإيقاف الطارئ</h2>
      <p>{policy ? policy.kill_switch ? "مفعّل" : "غير مفعّل" : "غير متاح"}</p>
      {policy?.kill_switch === false && <button className={opsOutline} disabled={busy} onClick={() => void stop()}>فعّل الإيقاف الطارئ</button>}
      <Link className={link} href="/risk">إعدادات سياسة المخاطر</Link>
    </article>
  </section>;
}

export function ProposalList({history = false}: {history?: boolean}) {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  useEffect(() => {
    setReady(false);
    ops<Draft[]>("orders/proposals?limit=100&offset=" + (page * 100)).then((rows) => {setDrafts(rows);setReady(true);})
      .catch((why: Error) => setError(why.message));
  }, [page]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);setError("");
    try {
      const draft = await ops<Draft>("orders/proposals", {
        key: crypto.randomUUID(), ticker: String(form.get("ticker")).trim().toUpperCase(), intent: form.get("intent"),
        source: form.get("source"), shares: form.get("shares") ? Number(form.get("shares")) : null, limit: form.get("limit") || null,
      });
      setDrafts((items) => [draft, ...items.filter((item) => item.id !== draft.id)]);
    } catch (why) {setError((why as Error).message);}
    finally {setLoading(false);}
  }
  const visible = history ? drafts : drafts.filter((item) => activeStates.includes(item.state));
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">{history ? "سجل مسودات الأوامر" : "مسودات الأوامر للمراجعة"}</h1><Navigation/>
    <p className="text-amber-300">المسودات تحليل مشروط للمراجعة. حالة الإرسال الرسمي محجوبة.</p>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {!history && <form className={opsPanel} onSubmit={submit}>
      <h2 className="font-bold">مسودة جديدة</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label>رمز السهم<input className={opsField} name="ticker" required maxLength={20} dir="ltr"/></label>
        <label>السيناريو<select className={opsField} name="intent">{Object.entries(intents).map(([value,text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>مصدر الحساب<select className={opsField} name="source">{Object.entries(sources).map(([value,text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>الكمية للمراجعة · اختياري<input className={opsField} type="number" min={1} max={1000000} name="shares"/></label>
        <label>السعر المحدد · اختياري<input className={opsField} type="number" min=".000001" step="any" name="limit"/></label>
      </div>
      <button className={opsButton} disabled={loading}>حضّر مسودة محلية</button>
    </form>}
    {!ready && !error && <p role="status">جاري تحميل المسودات…</p>}
    {ready && !visible.length && <p className="text-gray-400">مفيش مسودات في العرض ده.</p>}
    {visible.map((draft) => <article key={draft.id} className={opsPanel}>
      <h2 className="font-bold"><bdi>{draft.ticker}</bdi> · {draft.company}</h2>
      <p>{intents[draft.intent]} · {orderLabel(draft.state)} · نسخة {draft.version}</p>
      <p className="text-sm text-gray-400">{orderLabel(draft.freshness)} · {timeLabel(draft.created)}</p>
      <Link className={link} href={"/orders/proposals/" + draft.id}>راجع التفاصيل</Link>
    </article>)}
    {(page > 0 || drafts.length === 100) && <div className="flex gap-2">
      <button className={opsOutline} disabled={page === 0} onClick={() => setPage((v) => v - 1)}>السابق</button>
      <button className={opsOutline} disabled={drafts.length < 100} onClick={() => setPage((v) => v + 1)}>التالي</button>
    </div>}
  </section>;
}

export function ProposalDetail({id}: {id: string}) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>();
  const [events, setEvents] = useState<Event[]>([]);
  const [consent, setConsent] = useState(false);
  const [challenge, setChallenge] = useState<{challenge: string; expires: number}>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const path = "orders/proposals/" + id;
  const reload = useCallback(async () => {
    const data = await ops<Draft>(path);
    setDraft(data);
    setEvents(await ops<Event[]>(path + "/events"));
  }, [path]);
  useEffect(() => {void reload().catch((why: Error) => setError(why.message));}, [reload]);
  async function act(action: () => Promise<void>) {
    setBusy(true);setError("");
    try {await action();}
    catch (why) {setError((why as Error).message);}
    finally {setBusy(false);}
  }
  const d = draft;
  const rows: [string, string | number | null | undefined][] = d ? [
    ["السهم", d.company], ["ISIN", d.isin], ["السوق والعملة", d.exchange + " · " + d.currency],
    ["الجانب", d.side === "BUY" ? "شراء" : "بيع"], ["نوع المسودة", d.order_type === "CONDITIONAL_LIMIT" ? "سيناريو بسعر محدد" : "مراجعة فقط"],
    ["الكمية المحسوبة", numberLabel(d.shares)], ["الكمية اللي طلبتها للمراجعة", numberLabel(d.requested_shares)], ["السعر المرجعي", numberLabel(d.reference)],
    ["السعر المحدد", numberLabel(d.limit)], ["المزوّد", d.provider], ["وقت الرصد", d.observation_at ? timeLabel(d.observation_at) : null],
    ["الجلسة المرجعية", d.reference_session],
    ["حداثة السعر", orderLabel(d.freshness)], ["القيمة التقديرية", numberLabel(d.costs.value)], ["العمولة التقديرية", numberLabel(d.costs.commission)],
    ["الضريبة التقديرية", numberLabel(d.costs.tax)], ["النقد المطلوب", numberLabel(d.costs.required_cash)], ["النقد المتبقي", numberLabel(d.cash_after)],
    ["القوة الشرائية المقدّرة من اللقطة", numberLabel(d.buying_power)], ["الكمية الحالية", numberLabel(d.held)], ["قابلة للبيع حسب اللقطة", numberLabel(d.sellable)],
    ["نطاق الدخول", d.entry_zone?.map(numberLabel).join(" — ")], ["الوقف", numberLabel(d.stop)], ["الأهداف", d.targets?.map(numberLabel).join(" · ")],
    ["المخاطرة المقدّرة", numberLabel(d.risk)], ["العائد إلى المخاطرة", numberLabel(d.reward_to_risk)],
    ["التعرّض قبل", numberLabel(d.before_exposure)], ["التعرّض بعد", numberLabel(d.after_exposure)], ["الفحص الشرعي", d.sharia],
    ["الإنشاء", timeLabel(d.created)], ["انتهاء الصلاحية", timeLabel(d.expires)],
  ] : [];

  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">مراجعة مسودة أمر</h1><Navigation/>
    {error && <p className="text-amber-300" role="alert">{error}</p>}
    {!d && !error && <p role="status">جاري تحميل المسودة…</p>}
    {d && <>
      <article className={opsPanel}>
        <h2 className="text-xl font-bold"><bdi>{d.ticker}</bdi> · {intents[d.intent]}</h2>
        <p>{orderLabel(d.state)} · النسخة {d.version} · {sources[d.source]}</p>
        <p className="text-amber-300">تحليل مشروط. راجع السعر والرسوم والتسوية داخل ثاندر بنفسك. الوقف قد يتنفذ بسعر مختلف.</p>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">{rows.map(([caption, value]) => <div className="min-w-0" key={caption}>
          <dt className="text-sm text-gray-400">{caption}</dt><dd className="break-words"><bdi>{value ?? "غير متاح"}</bdi></dd></div>)}</dl>
        {d.broker_quote && <p className="text-sm">رصد ثاندر · {numberLabel(d.broker_quote.price)} · {orderLabel(d.broker_quote.freshness)} · {timeLabel(d.broker_quote.observation_at)}</p>}
        <p>{d.explanation}</p>{d.ai_explanation && <p>{d.ai_explanation}</p>}
        <details><summary className="min-h-10 cursor-pointer font-semibold">الأدلة والمخاطر</summary>
          <ul className="list-disc space-y-1 ps-5">{[...d.supporting, ...d.opposing, ...d.scenario_blockers.map(orderLabel)].map((item, i) => <li key={i}>{item}</li>)}</ul>
          <p className="pt-2 text-sm text-gray-400">النسخة تفقد صلاحيتها لو اتغيرت سياسة المخاطر أو بيانات الجلسة والسعر، أو لما تنتهي مدة المراجعة.</p>
        </details>
      </article>
      <article className={opsPanel}><h2 className="font-bold">المراجعة والتسليم اليدوي</h2>
        <p>حالة الوسيط · {orderLabel(d.broker.submission)} · التنفيذ {orderLabel(d.broker.execution_status)}</p>
        <div className="flex flex-wrap gap-2">
          {["BLOCKED","APPROVAL_REQUIRED"].includes(d.state) && <button className={opsOutline} disabled={busy} onClick={() => void act(async () => {
            setConsent(false);setChallenge(await ops(path + "/review", {fingerprint: d.fingerprint}));
          })}>ابدأ المراجعة المحلية</button>}
          {d.state !== "CANCELLED" && <button className={opsOutline} disabled={busy} onClick={() => void act(async () => {
            const updated = await ops<Draft>(path + "/refresh", {key: crypto.randomUUID(), ticker: d.ticker, intent: d.intent,
              source: d.source, shares: d.requested_shares, limit: d.requested_limit ?? null});
            router.push("/orders/proposals/" + encodeURIComponent(updated.id));
          })}>حدّث التحليل</button>}
          {activeStates.includes(d.state) && <button className={opsOutline} disabled={busy} onClick={() => void act(async () => {
            await ops(path + "/reject", {});setChallenge(undefined);await reload();
          })}>ارفض المسودة</button>}
          <button className={opsButton} disabled aria-describedby="handoff-help">الإرسال الرسمي</button>
          <a href={official} className={link} target="_blank" rel="noopener noreferrer">موقع ثاندر الرسمي</a>
        </div>
        <p id="handoff-help" className="text-sm text-gray-400">افتح تطبيق ثاندر يدويًا من جهازك لو عايز تراجع السعر أو حالة أوامرك. المسودة لا تنتقل للتطبيق.</p>
        {challenge && <div className="space-y-2">
          <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)}/>
            راجعت النسخة دي وعارف إن التأكيد محفوظ هنا فقط.</label>
          <p className="text-sm text-gray-400">الرمز صالح لحد {timeLabel(challenge.expires)}</p>
          <button className={opsButton} disabled={!consent || busy} onClick={() => void act(async () => {
            await ops(path + "/confirm-local", {fingerprint: d.fingerprint, challenge: challenge.challenge, understood: true});
            setChallenge(undefined);await reload();
          })}>أكد المراجعة المحلية</button>
        </div>}
      </article>
      <article className={opsPanel}><h2 className="font-bold">سجل النسخة</h2>
        {events.map((event, i) => <p className="text-sm" key={i}>{orderLabel(event.kind)} · {timeLabel(event.created)} {event.reason && " · " + orderLabel(event.reason)}</p>)}
      </article>
      {d.readiness && <details><summary className="min-h-11 cursor-pointer font-bold">أسباب حجب الإرسال</summary><CheckList report={d.readiness}/></details>}
    </>}
  </section>;
}
