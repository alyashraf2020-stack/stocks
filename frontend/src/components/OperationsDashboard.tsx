"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { label, timeLabel, numberLabel, ops, opsOutline, opsPanel } from "@/lib/operations";

type Pulse = {running: boolean; configured: boolean; seen?: number};
type Snapshot = {equity?: number; cash?: number; as_of?: string; holdings: {ticker: string; shares?: number}[]};
type Review = {ticker: string; category: string; sharia?: string};
type Overview = {
  fastapi: string; database: string; migration?: {current?: string; expected: string; ready: boolean};
  workers?: Record<string, Pulse>;
  market?: {session_status: string; completed_session: string | null; version: string; coverage: string[]};
  policy?: {kill_switch: boolean; islamic: boolean};
  thndr?: {status: string; last_sync?: string};
  ai?: {status: string; model?: string; monthly_limit_usd: number; usage?: {monthly_estimated_usd?: number}};
  channels?: Record<string, {configured: boolean; enabled: boolean; destinations: number; last_ok?: number; PENDING?: number; FAILED?: number}>;
  data?: {approved_datasets: number; latest?: string};
  failed?: Record<string, number>;
  opportunities?: Review[]; reviews?: Review[];
  notifications?: {category: string; created: number}[];
  virtual?: {name: string; equity: number | null; realized: number}[];
  backtests?: {id: string; status: string; progress: number}[]; manual?: Snapshot;
};

const names: Record<string, string> = { scanner: "الماسح", paper: "التداول الافتراضي", backtest: "الاختبار التاريخي",
  notifications: "الإشعارات", import: "استيراد الجلسات", scan: "جولات الماسح", delivery: "الإرسال" };
const marketNames: Record<string, string> = { CLOSED: "الجلسة مقفولة حسب التقويم", OPEN: "وقت تداول مجدول",
  PRE_MARKET: "قبل الجلسة", HALTED: "إيقاف تداول", UNKNOWN: "الحالة اللحظية غير متحققة" };
const link = "inline-flex min-h-11 items-center text-sm font-semibold text-primary underline";

function AccountView({account}: {account?: Snapshot}) {
  return account && <div className="space-y-2 text-sm">
    <p>القيمة {numberLabel(account.equity)} ج.م · النقد {numberLabel(account.cash)} ج.م</p>
    <p className="text-gray-400">{timeLabel(account.as_of)}</p>
    <ul className="flex flex-wrap gap-2">{account.holdings.map((h) => <li key={h.ticker} className="rounded-lg bg-background px-2 py-1">
      <bdi>{h.ticker}</bdi> · {numberLabel(h.shares)} سهم
    </li>)}</ul>
  </div>;
}

export default function OperationsDashboard({full = false}: {full?: boolean}) {
  const [state, setState] = useState<Overview>();
  const [broker, setBroker] = useState<Snapshot>();
  const [error, setError] = useState("");
  const [brokerError, setBrokerError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true;
    function query() {
      ops<Overview>("system").then((data) => { if (live) { setState(data); setError(""); } })
        .catch((why: Error) => { if (live) { setError(why.message); setState(undefined); } });
    }
    query();
    const interval = full ? window.setInterval(query, 15000) : undefined;
    return () => { live = false; if (interval) window.clearInterval(interval); };
  }, [full, refresh]);
  async function loadBroker() {
    setBusy(true); setBrokerError(""); setBroker(undefined);
    try {
      const data = await ops<{total_value?: number; available_cash?: number; last_sync?: string;
        holdings?: {ticker: string; quantity?: number}[]}>("integrations/thndr/portfolio");
      if (!data.last_sync) throw new Error("مفيش لقطة ثاندر مصرح بيها متاحة.");
      setBroker({equity: data.total_value, cash: data.available_cash, as_of: data.last_sync,
        holdings: (data.holdings ?? []).slice(0, 6).map((h) => ({ticker: h.ticker, shares: h.quantity}))});
    } catch (why) { setBrokerError((why as Error).message); }
    finally { setBusy(false); }
  }
  return <section dir="rtl" className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      {full ? <h1 className="text-3xl font-bold">حالة تشغيل النظام</h1> : <h2 className="text-2xl font-bold">لوحة متابعة البورصة</h2>}
      {full ? <button className={opsOutline} onClick={() => setRefresh((i) => i + 1)}>تحديث الحالة</button> : <Link className={link} href="/system">حالة التشغيل</Link>}
    </div>
    {error && <p role="alert" className="text-sm text-amber-300">{error}</p>}
    {!state && !error && <p role="status" className="text-sm text-gray-400">جاري تحميل الحالة…</p>}
    {state && <>
      {state.migration?.ready !== true && <p role="alert" className="text-amber-300">قاعدة البيانات تحتاج مراجعة أو ترحيل. {state.migration?.current ?? ""}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article className={opsPanel}><h3 className="font-bold">السوق والبيانات</h3>
          <p>{marketNames[state.market?.session_status ?? "UNKNOWN"]}</p>
          <p className="text-sm">آخر جلسة <bdi>{state.market?.completed_session ?? "غير متاحة"}</bdi></p>
          <p className="text-sm">آخر توقيت مصدر معتمد {timeLabel(state.data?.latest)}</p>
          <p className="text-sm text-amber-300">التسعير اللحظي المتحقق منه غير متاح.</p>
          <Link href="/data" className={link}>تغطية البيانات ومصادرها</Link>
        </article>
        <article className={opsPanel}><h3 className="font-bold">ثاندر · بيانات وساطة</h3>
          <p>{label(state.thndr?.status)} · {timeLabel(state.thndr?.last_sync)}</p>
          {state.thndr?.status === "CONNECTED" && <button className={opsOutline} disabled={busy} onClick={() => void loadBroker()}>عرض اللقطة المصرح بيها</button>}
          {brokerError && <p className="text-amber-300">{brokerError}</p>}<AccountView account={broker}/>
          <Link href="/portfolio" className={link}>المحفظة والمزامنة</Link>
        </article>
        <article className={opsPanel}><h3 className="font-bold">المخاطر والفرز الشرعي</h3>
          <p className={state.policy?.kill_switch ? "text-amber-300" : "text-gray-300"}>
            الإيقاف الطارئ {state.policy ? state.policy.kill_switch ? "مفعّل" : "غير مفعّل" : "غير متاح"}</p>
          <p>الوضع الإسلامي {state.policy ? state.policy.islamic ? "مفعّل" : "غير مفعّل" : "غير متاح"}</p>
          <div className="flex flex-wrap gap-4"><Link href="/risk" className={link}>راجع المخاطر</Link><Link href="/sharia" className={link}>راجع الفحص</Link></div>
        </article>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article className={opsPanel}><h3 className="font-bold">الخدمات</h3>
          {full && <p className="text-sm">FastAPI {label(state.fastapi)} · قاعدة البيانات {label(state.database)}</p>}
          {Object.entries(state.workers ?? {}).map(([role, pulse]) => <p key={role} className="text-sm">
            {names[role] ?? role} · <span className={pulse.running ? "text-emerald-300" : "text-amber-300"}>{pulse.running ? "شغّال" : "مفيش نبضة حديثة"}</span>
            {full && <span className="text-gray-400"> · {timeLabel(pulse.seen)} · {pulse.configured ? "مهيّأ" : "متوقف من الإعدادات"}</span>}
          </p>)}
          <p className="text-sm">OpenAI · {label(state.ai?.status)} <bdi>{state.ai?.model}</bdi></p>
          {full && state.ai && <p className="text-sm text-gray-400">ميزانية الشهر {state.ai.monthly_limit_usd} دولار · الاستهلاك {numberLabel(state.ai.usage?.monthly_estimated_usd)}</p>}
        </article>
        <article className={opsPanel}><h3 className="font-bold">الإشعارات</h3>
          {Object.entries(state.channels ?? {}).map(([key, item]) => <p key={key} className="text-sm">
            {key === "TELEGRAM" ? "تيليجرام" : "المتصفح"} · {item.enabled ? "مفعّل" : "متوقف"} · {item.configured ? "مهيّأ" : "يحتاج إعداد"} · {item.destinations} وجهة
            {full && <span className="block text-gray-400">آخر إرسال {timeLabel(item.last_ok)} · {item.FAILED ?? 0} فشل · {item.PENDING ?? 0} معلّق</span>}
          </p>)}
          <Link href="/settings/notifications" className={link}>الإعدادات والإرسال</Link>
        </article>
        <article className={opsPanel}><h3 className="font-bold">{full ? "الأعطال والتغطية" : "فرص ومراجعات"}</h3>
          {full ? <>
            <p className="text-sm">الترحيل <bdi>{state.migration?.current ?? "غير متاح"}</bdi></p>
            <p className="text-sm">التقويم {state.market?.version} · <bdi>{state.market?.coverage.join(" — ")}</bdi></p>
            <p className="text-sm">حزم الأسهم المؤهلة {state.data?.approved_datasets ?? "–"}</p>
            {Object.entries(state.failed ?? {}).map(([key, value]) => <p className="text-sm" key={key}>{names[key] ?? key} · {value} فشل</p>)}
          </> : <>
            {!(state.opportunities?.length || state.reviews?.length) && <p className="text-sm text-gray-400">مفيش إشارات حالية محفوظة.</p>}
            {[...(state.opportunities ?? []), ...(state.reviews ?? [])].slice(0, 6).map((item) =>
              <p className="text-sm" key={item.ticker}><bdi>{item.ticker}</bdi> · {label(item.category)} {item.sharia && <small>· {label(item.sharia)}</small>}</p>)}
            <div className="flex flex-wrap gap-3"><Link href="/opportunities" className={link}>الفرص بالتفصيل</Link><Link href="/orders/proposals" className={link}>مسودات الأوامر</Link></div>
          </>}
        </article>
      </div>
      {!full && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {state.manual && <article className={opsPanel}><h3 className="font-bold">لقطة مدخلة يدويًا</h3><AccountView account={state.manual}/></article>}
        <article className={opsPanel}><h3 className="font-bold">أرصدة افتراضية</h3>
          {state.virtual?.map((v) => <p className="text-sm" key={v.name}>{v.name} · {numberLabel(v.equity)} ج.م · محقق {numberLabel(v.realized)}</p>)}
          {!state.virtual?.length && <p className="text-sm text-gray-400">مفيش حسابات افتراضية نشطة.</p>}
          <Link href="/paper-trading" className={link}>التداول الافتراضي</Link>
        </article>
        <article className={opsPanel}><h3 className="font-bold">الاختبارات التاريخية</h3>
          {state.backtests?.map((r) => <div key={r.id}><Link href={"/backtesting/results/" + r.id} className={link}>{label(r.status)} · {r.progress}%</Link></div>)}
          {!state.backtests?.length && <p className="text-sm text-gray-400">مفيش اختبارات محفوظة.</p>}
          <Link href="/backtesting/results" className={link}>كل النتائج</Link>
        </article>
        <article className={opsPanel}><h3 className="font-bold">آخر التنبيهات</h3>
          {state.notifications?.map((item, i) => <p className="text-sm" key={i}>{label(item.category)} · {timeLabel(item.created)}</p>)}
          {!state.notifications?.length && <p className="text-sm text-gray-400">مفيش تنبيهات معروضة.</p>}
          <Link href="/notifications" className={link}>افتح التنبيهات</Link>
        </article>
      </div>}
    </>}
    {full && <div className="flex flex-wrap gap-4">
      <Link href="/settings/system" className={link}>الوصول والتثبيت</Link><Link href="/data" className={link}>جاهزية البيانات</Link>
      <Link href="/settings/devices" className={link}>الأجهزة</Link>
    </div>}
  </section>;
}
