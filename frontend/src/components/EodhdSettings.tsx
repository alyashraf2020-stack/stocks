"use client";

import { FormEvent, useEffect, useState } from "react";
import { label, ops, opsButton, opsField, opsOutline, opsPanel, timeLabel } from "@/lib/operations";

type Options = { enabled: boolean; automatic: boolean; retry: boolean; exclusive: boolean };
type Status = Options & {
  configured: boolean;
  connection: string | null;
  checked_at: number | null;
  utc_day: string;
  resets_at: string;
  limit: number;
  reserved: number;
  account_used: number | null;
  remaining: number;
  mapped: number;
  completed_session: string | null;
  symbols: {
    ticker: string; status: string; freshness: string; last_session: string | null; last_attempt: number;
  }[];
};

const path = "data/eodhd";
const flags: [keyof Options, string][] = [
  ["exclusive", "الحساب مخصص للتطبيق ومش بستخدم نفس حساب EODHD في طلبات تانية أثناء المزامنة."],
  ["enabled", "فعّل مزوّد EODHD"],
  ["automatic", "زامن تلقائيًا بعد اكتمال جلسات البورصة"],
  ["retry", "أعد المحاولة تلقائيًا عند تعطل مؤقت، في حدود الرصيد اليومي"],
];

export default function EodhdSettings() {
  const [status, setStatus] = useState<Status>();
  const [options, setOptions] = useState<Options>();
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    ops<Status>(path).then((data) => {
      if (current) { setStatus(data); setOptions(data); }
    }).catch((err: Error) => { if (current) setError(err.message); });
    return () => { current = false; };
  }, []);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setFeedback("");
    try { setFeedback(await action()); }
    catch (err) { setError((err as Error).message); }
    finally {
      try { setStatus(await ops<Status>(path)); }
      catch (err) { setError((err as Error).message); }
      setBusy(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!options) return;
    const form = event.currentTarget;
    const field = form.elements.namedItem("token") as HTMLInputElement;
    const token = field.value.trim();
    field.value = "";
    await run(async () => {
      const updated = await ops<Status>(path + "/settings", {
        enabled: options.enabled, automatic: options.automatic, retry: options.retry, exclusive: options.exclusive,
        ...(token ? { token } : {}),
      });
      setOptions(updated);
      return "الإعدادات اتحفظت.";
    });
  }

  function trigger(action: string, body: object = {}) {
    return run(async () => {
      const result = await ops<{ status: string; added?: number }>(path + "/" + action, body);
      return label(result.status) + (result.added == null ? "" : ` · ${result.added} شمعة جديدة`);
    });
  }

  return <section id="eodhd" dir="rtl" className={opsPanel}>
    <h2 className="text-xl font-bold">EODHD المجاني</h2>
    <p>شموع يومية بعد إغلاق البورصة. البيانات للتحليل والمراجعة، وأهلية التنفيذ بتحتاج بيانات إضافية.</p>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {feedback && <p role="status">{feedback}</p>}
    {status && options && <>
      <div className="grid gap-2 sm:grid-cols-2">
        <p>المزوّد {status.enabled ? "مفعّل" : "متوقف"} · المفتاح {status.configured ? "محفوظ مشفّر" : "غير محفوظ"}</p>
        <p>آخر اتصال {label(status.connection)} · {timeLabel(status.checked_at)}</p>
        <p>محجوز من التطبيق <bdi>{status.reserved}/{status.limit}</bdi> · المتاح حسب آخر تحقق <bdi>{status.remaining}</bdi></p>
        <p>آخر عدّاد للحساب <bdi>{status.account_used ?? "غير متحقق منه"}</bdi> · إعادة الضبط <bdi>{status.resets_at}</bdi></p>
        <p>رموز الدليل <bdi>{status.mapped}</bdi> · آخر جلسة مكتملة <bdi>{status.completed_session ?? "غير متاحة"}</bdi></p>
      </div>
      <form onSubmit={save} className="space-y-2">
        <label className="block">مفتاح API جديد
          <input className={opsField} name="token" type="password" autoComplete="off" maxLength={256} dir="ltr"
            placeholder={status.configured ? "سيبه فاضي لو المفتاح زي ما هو" : "مفتاح حسابك المجاني"} />
        </label>
        {flags.map(([key, text]) => <label key={key} className="flex min-h-10 items-center gap-2">
          <input type="checkbox" checked={options[key]} disabled={busy || key === "automatic" && !options.enabled}
            onChange={(ev) => {
              const checked = ev.target.checked;
              setOptions({ ...options, [key]: checked, ...(key === "enabled" && !checked ? { automatic: false } : {}) });
            }} />
          {text}
        </label>)}
        <button className={opsButton} disabled={busy}>حفظ الإعدادات</button>
      </form>
      <div className="flex flex-wrap gap-2">
        <button className={opsOutline} disabled={!status.configured || busy} onClick={() => void trigger("test")}>اختبر الاتصال مجانًا</button>
        <button className={opsOutline} disabled={!status.enabled || busy} onClick={() => void trigger("catalog")}>حدّث دليل الرموز · وحدة واحدة</button>
        <button className={opsOutline} disabled={!status.configured || busy} onClick={() => void run(async () => {
          const data = await ops<Status>(path + "/disconnect", {});
          setOptions(data);
          return "المفتاح اتمسح والمزامنة وقفت. الأسعار اللي اتحفظت لسه متاحة للتحليل.";
        })}>امسح المفتاح وأوقف المزوّد</button>
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        void trigger("sync", { ticker: String(data.get("ticker")).trim().toUpperCase() });
      }}>
        <label>رمز سهم EGX
          <input className={opsField} name="ticker" dir="ltr" placeholder="SWDY" required maxLength={20} />
        </label>
        <button className={opsButton} disabled={!status.enabled || busy}>زامن إغلاق السهم · وحدة واحدة عند الطلب</button>
      </form>
      {status.symbols.length > 0 && <ul className="divide-y divide-surfaceBorder">
        {status.symbols.map((row) => <li key={row.ticker} className="py-2">
          <bdi>{row.ticker}</bdi> · {label(row.freshness)} · <bdi>{row.last_session ?? "—"}</bdi>
          <span className="block text-sm text-gray-400">{label(row.status)} · {timeLabel(row.last_attempt)}</span>
        </li>)}
      </ul>}
    </>}
  </section>;
}
