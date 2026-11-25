"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { alertCategories, label, ops, opsButton, opsField, opsOutline, opsPanel, timeLabel } from "@/lib/operations";

type Preferences = {
  in_app: boolean; telegram: boolean; push: boolean; detailed: boolean; severity: string; muted: string[];
  quiet_start: number | null; quiet_end: number | null; critical_bypass: boolean; cooldown: number; revision: number;
};
type Target = {id: string; channel: "TELEGRAM" | "PUSH"; label: string; active: boolean; since: number; last_ok?: number};
type Settings = {
  preferences: Preferences; configured: Record<"TELEGRAM" | "PUSH", boolean>; vapid_public_key: string | null; targets: Target[];
  recent: {channel: string; status: string; error?: string; created: number; attempts: number; history: {at: number; result: string}[]}[];
  delivery_counts: Record<string, Record<string, number>>;
};
const severities: Record<string, string> = {INFO: "معلومة", OPPORTUNITY: "فرصة للمراجعة", WARNING: "تنبيه", CRITICAL: "حرج"};
const channelName = {TELEGRAM: "تيليجرام", PUSH: "إشعار المتصفح"};
const path = "notification-settings";
const link = "inline-flex min-h-11 items-center text-primary underline";

function clockInput(minutes: number | null) {
  if (minutes == null) return "";
  return String(Math.floor(minutes / 60)).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0");
}
function minutesInput(text: string) {
  if (!text) return null;
  const [hours, minutes] = text.split(":").map(Number);
  return 60 * hours + minutes;
}
function vapidKey(encoded: string) {
  const value = encoded.replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(value.padEnd(Math.ceil(value.length / 4) * 4, "=")), (char) => char.charCodeAt(0));
}

export default function DeliverySettings({ devices = false }: {devices?: boolean}) {
  const [settings, setSettings] = useState<Settings>();
  const [pair, setPair] = useState<{url: string; expires: number}>();
  const [name, setName] = useState("");
  const [supported, setSupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() { setSettings(await ops<Settings>(path)); }
  useEffect(() => {
    setSupported(window.isSecureContext && "Notification" in window && "serviceWorker" in navigator && "PushManager" in window);
    void refresh().catch((why: Error) => setError(why.message));
  }, []);

  async function perform(task: () => Promise<void>, message = "") {
    setBusy(true); setError(""); setNotice("");
    try { await task(); setNotice(message); }
    catch (why) { setError((why as Error).message); }
    finally { setBusy(false); }
  }
  function edit(part: Partial<Preferences>) {
    setSettings((s) => s ? {...s, preferences: {...s.preferences, ...part}} : s);
  }
  async function subscribe() {
    if (!settings?.vapid_public_key || !supported) return;
    await perform(async () => {
      if (await Notification.requestPermission() !== "granted") throw new Error("اسمح بالإشعارات من إعدادات المتصفح الأول.");
      const registration = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("التطبيق لسه بيجهّز عامل الخدمة. حدّث الصفحة.")), 8000)),
      ]);
      const existing = await registration.pushManager.getSubscription();
      const subscription = existing ?? await registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: vapidKey(settings.vapid_public_key as string),
      });
      const payload = subscription.toJSON();
      try {
        await ops(path + "/devices", {endpoint: payload.endpoint, keys: payload.keys, name: name.trim() || "جهاز المتصفح"});
      } catch (why) {
        if (!existing) await subscription.unsubscribe().catch(() => false);
        throw why;
      }
      await refresh();
    }, "الجهاز اتسجّل. فعّل قناة المتصفح من إعدادات التنبيهات.");
  }
  function changeTarget(target: Target, operation: "revoke" | "test") {
    void perform(async () => {
      await ops(path + "/targets/" + target.id + "/" + operation + (operation === "test" ? "?channel=" + target.channel : ""), {});
      if (operation === "revoke" && target.channel === "PUSH" && supported) {
        const registration = await navigator.serviceWorker.getRegistration();
        const sub = await registration?.pushManager.getSubscription();
        if (sub) {
          const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(["PUSH", sub.endpoint])));
          const id = Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
          if (id === target.id) await sub.unsubscribe();
        }
      }
      await refresh();
    }, operation === "revoke" ? "الوجهة اتلغت." : "اتضاف اختبار الإرسال لطابور العامل.");
  }

  const pref = settings?.preferences;
  const targets = settings?.targets.filter((item) => devices ? item.channel === "PUSH" : item.channel === "TELEGRAM") ?? [];
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">{devices ? "الأجهزة والإشعارات" : "إعدادات التنبيهات"}</h1>
    <nav className="flex flex-wrap gap-4"><Link href="/settings/notifications" className={link}>تفضيلات التنبيهات</Link>
      <Link href="/settings/devices" className={link}>الأجهزة</Link><Link href="/notifications" className={link}>التنبيهات</Link></nav>
    {error && <p className="text-amber-300" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!settings && !error && <p role="status">جاري تحميل الإعدادات…</p>}
    {!devices && pref && <form className={opsPanel} onSubmit={(event) => {
      event.preventDefault(); void perform(async () => { await ops(path, pref); await refresh(); }, "اتحفظت التفضيلات.");
    }}>
      <h2 className="text-xl font-bold">القنوات والخصوصية</h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {([["in_app", "داخل التطبيق"], ["telegram", "تيليجرام"], ["push", "إشعارات المتصفح"],
          ["detailed", "اعرض الرمز ووقت الرصد في التنبيه الخارجي"], ["critical_bypass", "اسمح للحرج بتجاوز ساعات الهدوء"]] as const)
          .map(([key, title]) => <label key={key} className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={pref[key]} onChange={(e) => edit({[key]: e.target.checked})}/>{title}
          </label>)}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1 text-sm">أقل شدة<select className={opsField} value={pref.severity} onChange={(e) => edit({severity: e.target.value})}>
          {Object.entries(severities).map(([key, title]) => <option key={key} value={key}>{title}</option>)}
        </select></label>
        <label className="space-y-1 text-sm">بداية الهدوء · القاهرة<input className={opsField} type="time" value={clockInput(pref.quiet_start)} onChange={(e) => edit({quiet_start: minutesInput(e.target.value)})}/></label>
        <label className="space-y-1 text-sm">نهاية الهدوء · القاهرة<input className={opsField} type="time" value={clockInput(pref.quiet_end)} onChange={(e) => edit({quiet_end: minutesInput(e.target.value)})}/></label>
        <label className="space-y-1 text-sm">الفاصل بين نفس النوع · دقائق<input className={opsField} type="number" min={0} max={1440} value={pref.cooldown / 60} onChange={(e) => edit({cooldown: Number(e.target.value) * 60})}/></label>
      </div>
      <details><summary className="flex min-h-11 cursor-pointer items-center font-semibold">فئات التنبيهات</summary>
        <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(alertCategories).map(([key, title]) =>
          <label key={key} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={!pref.muted.includes(key)} onChange={(e) =>
            edit({muted: e.target.checked ? pref.muted.filter((item) => item !== key) : [...pref.muted, key]})}/>{title}</label>)}</div>
      </details>
      <button className={opsButton} disabled={busy}>حفظ التفضيلات</button>
    </form>}
    {settings && <article className={opsPanel}>
      <h2 className="text-xl font-bold">{devices ? "ربط جهاز" : "ربط تيليجرام"}</h2>
      {devices ? <>
        {!supported && <p className="text-amber-300">الإذن غير متاح هنا. على iPhone افتح التطبيق من الشاشة الرئيسية، أو استخدم تيليجرام أو التطبيق.</p>}
        {!settings.configured.PUSH && <p className="text-sm text-gray-400">VAPID محتاج إعداد على الخادم.</p>}
        <label className="block max-w-md space-y-1 text-sm">اسم الجهاز<input className={opsField} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="موبايل شخصي"/></label>
        <button className={opsButton} disabled={!supported || !settings.configured.PUSH || busy} onClick={() => void subscribe()}>اسمح وسجّل الجهاز</button>
      </> : <>
        <p>{settings.configured.TELEGRAM ? "البوت مهيأ. اربط محادثتك الخاصة بكود مدته عشر دقايق." : "البوت محتاج إعداد على الخادم."}</p>
        <div className="flex flex-wrap gap-3">
          <button className={opsButton} disabled={busy || !settings.configured.TELEGRAM} onClick={() => void perform(async () => {
            setPair(await ops(path + "/telegram/pair", {}));
          })}>ابدأ ربط جديد</button>
          {pair && <>
            <a className={link} href={pair.url} target="_blank" rel="noopener noreferrer">افتح البوت واضغط Start</a>
            <button className={opsOutline} disabled={busy} onClick={() => void perform(async () => {
              const result = await ops<{paired: boolean}>(path + "/telegram/check", {});
              if (!result.paired) throw new Error("رسالة Start لسه ما وصلتش. افتح المحادثة واضغط Start.");
              setPair(undefined); await refresh();
            }, "المحادثة الخاصة اتربطت.")}>تحقق من الربط</button>
          </>}
        </div>
        {pair && <p className="text-sm text-gray-400">صالح لحد {timeLabel(pair.expires)}</p>}
      </>}
      {targets.map((target) => <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surfaceBorder pt-3" key={target.id}>
        <div><p>{target.label} · {target.active ? "مصَرّح" : "ملغي"}</p><p className="text-sm text-gray-400">آخر إرسال {timeLabel(target.last_ok)}</p></div>
        {target.active && <div className="flex flex-wrap gap-2">
          <button className={opsOutline} disabled={busy} onClick={() => changeTarget(target, "test")}>اختبار الإرسال</button>
          <button className={opsOutline} disabled={busy} onClick={() => changeTarget(target, "revoke")}>إلغاء الربط</button>
        </div>}
      </div>)}
    </article>}
    {settings && <article className={opsPanel}><div className="flex flex-wrap justify-between gap-2">
      <h2 className="text-lg font-bold">سجل الإرسال</h2><button className={opsOutline} disabled={busy} onClick={() => void perform(refresh)}>تحديث السجل</button>
    </div>
      {Object.entries(settings.delivery_counts).map(([key, counts]) => <p key={key} className="text-sm">
        {channelName[key as Target["channel"]]} · {counts.PENDING ?? 0} معلّق · {counts.DELIVERED ?? 0} اتسلّم · {counts.FAILED ?? 0} فشل
      </p>)}
      {settings.recent.map((row, index) => <details className="border-t border-surfaceBorder pt-2 text-sm" key={index}>
        <summary className="cursor-pointer">{channelName[row.channel as Target["channel"]]} · {label(row.status)} · {row.attempts} محاولة · {timeLabel(row.created)}</summary>
        {row.error && <p className="text-amber-300">{label(row.error)}</p>}
        {row.history.map((attempt, i) => <p key={i}>{timeLabel(attempt.at)} · {label(attempt.result)}</p>)}
      </details>)}
    </article>}
  </section>;
}
