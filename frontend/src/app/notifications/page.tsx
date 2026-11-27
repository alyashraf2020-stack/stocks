"use client";

import Link from "next/link";
import { alertCategories } from "@/lib/operations";

import { useEffect, useState } from "react";
import ScannerNavigation from "@/components/ScannerNavigation";
import { reason } from "@/lib/risk";
import { freshnessLabel } from "@/lib/thndr";
import { Alert, categories, messages, scannerRequest, scannerTime, severity } from "@/lib/scanner";

export default function NotificationsPage() {
  const [alerts, setAlerts] = useState<Alert[]>();
  const [unread, setUnread] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    scannerRequest<Alert[]>("notifications?unread=" + unread).then((data) => {
      if (active) { setAlerts(data); setError(""); }
    }).catch((e: Error) => {
      if (active) { setAlerts(undefined); setError(e.message); }
    });
    return () => { active = false; };
  }, [unread, refresh]);

  async function mark(id: string, acknowledge: boolean) {
    try {
      await scannerRequest("notifications/" + id, { read: true, acknowledge });
      setRefresh((n) => n + 1);
    } catch (e) { setError((e as Error).message); }
  }
  return (
    <section dir="rtl" className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-3xl font-bold">التنبيهات</h1>
      <ScannerNavigation />
      <div className="flex flex-wrap gap-3 text-primary">
        <Link className="inline-flex min-h-11 items-center underline" href="/settings/notifications">إعدادات التنبيهات</Link>
        <Link className="inline-flex min-h-11 items-center underline" href="/settings/devices">الأجهزة</Link>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2"><input type="checkbox" checked={unread} onChange={(e) => setUnread(e.target.checked)} /> غير المقروءة فقط</label>
        <button className="text-primary underline" onClick={() => setRefresh((n) => n + 1)}>تحديث</button>
      </div>
      {error && <p role="alert" className="text-amber-300">{error}</p>}
      {alerts && !alerts.length && <p className="text-gray-400">مفيش تنبيهات للعرض.</p>}
      {alerts?.map((alert) => <article key={alert.id} className="space-y-2 rounded-xl border border-surfaceBorder bg-surface p-4">
        <div className="flex flex-wrap justify-between gap-2">
          <h2 className="font-bold">{categories[alert.category] ?? alertCategories[alert.category]} {alert.ticker && <bdi>· {alert.ticker}</bdi>}</h2>
          <span className={alert.severity === "WARNING" || alert.severity === "CRITICAL" ? "text-amber-300" : "text-gray-300"}>{severity[alert.severity]}</span>
        </div>
        <p>{messages[alert.reason] ?? categories[alert.reason] ?? reason(alert.reason)}</p>
        <p className="text-sm text-gray-400">اتسجّل {scannerTime(alert.created)} · وقت الرصد {scannerTime(alert.source_timestamp)} · {alert.provider === "EODHD" && alert.freshness === "HISTORICAL" ? "إغلاق يومي متحقّق من EODHD" : freshnessLabel[alert.freshness]}</p>
        {alert.requires_recheck && <p className="text-sm text-amber-300">مراجعة تاريخية. راجع الأسعار والقواعد الحالية قبل الاعتماد على الإشارة.</p>}
        {alert.limitations.filter((code) => !["REVIEW_ONLY", "NO_VERIFIED_LIVE_SESSION"].includes(code)).map((code) => <p key={code} className="text-sm text-gray-400">{messages[code] ?? reason(code)}</p>)}
        <div className="flex gap-4 text-sm text-primary">
          {!alert.read_at && <button className="underline" onClick={() => mark(alert.id, false)}>تحديد كمقروء</button>}
          {!alert.acknowledged_at && <button className="underline" onClick={() => mark(alert.id, true)}>تأكيد المراجعة</button>}
          {alert.acknowledged_at && <span className="text-gray-400">اتراجَع</span>}
        </div>
      </article>)}
    </section>
  );
}
