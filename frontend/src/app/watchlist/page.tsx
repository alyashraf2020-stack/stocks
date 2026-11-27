"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import ScannerNavigation from "@/components/ScannerNavigation";
import { ScannerSettings, scannerRequest } from "@/lib/scanner";

export default function WatchlistPage() {
  const [settings, setSettings] = useState<ScannerSettings>();
  const [symbols, setSymbols] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    scannerRequest<ScannerSettings>("scanner/settings").then((data) => {
      setSettings(data); setSymbols(data.watchlist.join("\n"));
    }).catch((e: Error) => setError(e.message));
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true); setMessage(""); setError("");
    try {
      const watchlist = Array.from(new Set(symbols.toUpperCase().split(/[\s,،]+/).filter(Boolean)));
      setSettings(await scannerRequest<ScannerSettings>("scanner/settings", { ...settings, watchlist }));
      setSymbols(watchlist.join("\n"));
      setMessage("اتحفظت قائمة المتابعة.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <section dir="rtl" className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-3xl font-bold">قائمة المتابعة</h1>
      <ScannerNavigation />
      <p className="text-gray-400">رتّب الرموز حسب أولويتك. مسح السوق بيبدأ بالقائمة دي لو الجولة لها حد أقصى.</p>
      <Link className="text-primary underline" href="/data/providers#eodhd">مزامنة إغلاقات قائمة المتابعة عبر EODHD</Link>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
      {message && <p role="status">{message}</p>}
      {settings && <form onSubmit={submit} className="space-y-4 rounded-xl border border-surfaceBorder bg-surface p-4">
        <label className="block">رموز الأسهم
          <textarea rows={8} dir="ltr" className="mt-2 w-full rounded border border-surfaceBorder bg-background p-3" value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="COMI" />
        </label>
        <button className="rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50" disabled={busy}>حفظ القائمة</button>
      </form>}
    </section>
  );
}
