"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import ScannerNavigation from "@/components/ScannerNavigation";
import { categories, modes, ScannerSettings, scannerRequest, severity } from "@/lib/scanner";

const field = "rounded border border-surfaceBorder bg-background p-2";

export default function ScannerSettingsPage() {
  const [settings, setSettings] = useState<ScannerSettings>();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    scannerRequest<ScannerSettings>("scanner/settings").then(setSettings).catch((e: Error) => setError(e.message));
  }, []);
  function change(patch: Partial<ScannerSettings>) {
    setSettings((current) => current ? { ...current, ...patch } : current);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true); setError(""); setNotice("");
    try {
      setSettings(await scannerRequest<ScannerSettings>("scanner/settings", settings));
      setNotice("اتحفظت إعدادات الماسح.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const alertCategories = Object.entries(categories).filter(([key]) => !["ENTRY_WATCH", "HOLDING_REVIEW", "RISK_BLOCKED", "SHARIA_BLOCKED", "UNAVAILABLE", "MONITOR", "KILL_SWITCH"].includes(key));
  return (
    <section dir="rtl" className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-3xl font-bold">إعدادات ماسح السوق</h1>
      <ScannerNavigation />
      {error && <p role="alert" className="text-amber-300">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {settings && <form onSubmit={save} className="space-y-5 rounded-xl border border-surfaceBorder bg-surface p-4">
        <label className="flex items-center gap-2"><input type="checkbox" checked={settings.enabled} onChange={(e) => change({ enabled: e.target.checked })} /> تفعيل الجدولة</label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-2">نطاق التحليل
            <select className={field} value={settings.mode} onChange={(e) => change({ mode: e.target.value })}>
              {Object.entries(modes).map(([key, label]) => <option key={key} value={key} disabled={key === "MANUAL_PORTFOLIO" && !settings.manual}>{label}</option>)}
            </select>
          </label>
          <label className="grid gap-2">موعد التحليل
            <select className={field} value={settings.interval_seconds} onChange={(e) => change({ interval_seconds: Number(e.target.value) })}>
              <option value={0}>بعد الجلسة المكتملة</option>
              {[1, 5, 15, 30].map((minutes) => <option key={minutes} value={minutes * 60} disabled>كل {minutes} دقيقة · محتاج مصدر مرخّص</option>)}
            </select>
          </label>
        </div>
        <p className="text-sm text-gray-400">احفظ بيانات المحفظة اليدوية من <Link href="/risk" className="text-primary underline">صفحة المخاطر</Link>. مراقبة ثاندر تستخدم آخر مزامنة متاحة بعد التحقق من الإذن. التنبيهات بتظهر داخل التطبيق.</p>
        <label className="grid gap-2 sm:max-w-xs">أقل درجة تنبيه
          <select className={field} value={settings.minimum_severity} onChange={(e) => change({ minimum_severity: e.target.value })}>
            {Object.entries(severity).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <fieldset className="grid gap-3 sm:grid-cols-2">
          <legend className="mb-2 font-bold">أنواع التنبيهات</legend>
          {alertCategories.map(([key, label]) => <label key={key} className="flex items-center gap-2">
            <input type="checkbox" checked={!settings.muted_categories.includes(key)} onChange={(e) => change({
              muted_categories: e.target.checked ? settings.muted_categories.filter((item) => item !== key) : [...settings.muted_categories, key],
            })} />{label}
          </label>)}
        </fieldset>
        <button className="rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50" disabled={busy}>حفظ الإعدادات</button>
      </form>}
    </section>
  );
}
