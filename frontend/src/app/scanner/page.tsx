"use client";

import { useEffect, useState } from "react";
import ScannerNavigation from "@/components/ScannerNavigation";
import ScannerResults from "@/components/ScannerResults";
import { Health, Job, messages, modes, ScannerSettings, scannerRequest, scannerTime, states } from "@/lib/scanner";

export default function ScannerPage() {
  const [health, setHealth] = useState<Health>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<number>();
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [status, history] = await Promise.all([
          scannerRequest<Health>("scanner/status"), scannerRequest<Job[]>("scanner/history"),
        ]);
        if (alive) { setHealth(status); setJobs(history); setError(""); }
      } catch (e) {
        if (alive) { setHealth(undefined); setError((e as Error).message); }
      }
    }
    void load();
    const timer = window.setInterval(load, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [refresh]);

  async function control(action: "toggle" | "run") {
    setBusy(true); setNotice(""); setError("");
    try {
      if (action === "toggle") {
        const current = await scannerRequest<ScannerSettings>("scanner/settings");
        await scannerRequest("scanner/settings", { ...current, enabled: !current.enabled });
        setNotice(current.enabled ? "اتوقفت الجدولة." : "اتفعّلت الجدولة. حالة العامل موضّحة تحت.");
      } else {
        const job = await scannerRequest<{ job_id: number }>("scanner/run", {});
        setNotice("اتضافت الجولة رقم " + job.job_id + " لطابور التشغيل.");
        setSelected(undefined);
      }
      setRefresh((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const summary = health?.last_summary;
  return (
    <section dir="rtl" className="space-y-6">
      <h1 className="text-3xl font-bold">ماسح السوق</h1>
      <ScannerNavigation />
      {error && <p className="text-amber-300" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {health && <>
        <div className="flex flex-wrap gap-3">
          <button className="rounded-lg bg-primary px-4 py-2 font-bold text-background disabled:opacity-50" disabled={busy} onClick={() => control("toggle")}>{health.enabled ? "إيقاف الجدولة" : "تشغيل الجدولة"}</button>
          <button className="rounded-lg border border-primary px-4 py-2 text-primary disabled:opacity-50" disabled={busy || health.interval_seconds !== 0} onClick={() => control("run")}>تشغيل جولة يدوية</button>
        </div>
        <dl className="grid grid-cols-2 gap-4 rounded-xl border border-surfaceBorder bg-surface p-4 sm:grid-cols-3 lg:grid-cols-4">
          {[
            ["الجدولة", health.enabled ? "مفعّلة" : "متوقفة"], ["العامل", health.worker_online ? "متصل" : "غير متصل"],
            ["آخر نبضة", scannerTime(health.last_heartbeat)], ["آخر جولة ناجحة", scannerTime(health.last_success)],
            ["موعد الجولة القادمة", scannerTime(health.next_scheduled)], ["وضع الماسح", modes[health.mode]],
            ["حالة السوق", states[health.market.session_status]], ["التقويم", health.market.version],
            ["آخر جلسة مكتملة", health.market.completed_session ?? "غير متاحة"],
            ["آخر مهمة", health.job_status ? states[health.job_status] : "غير متاحة"],
            ["تنبيهات نشطة", String(health.active_alerts)], ["مصدر الماسح", "الجلسات المكتملة في الكاش المحلي"],
          ].map(([label, value]) => <div key={label}><dt className="text-sm text-gray-400">{label}</dt><dd>{value}</dd></div>)}
        </dl>
        <p className="text-sm text-gray-400">{messages[health.intraday_blocker]} التقويم يغطي {health.market.coverage.join(" إلى ")}. حالة التداول اللحظية غير مؤكدة.</p>
        {health.job_error && <p className="text-amber-300" role="status">{messages[health.job_error] ?? health.job_error}</p>}
        {summary && <div className="space-y-2 rounded-xl border border-surfaceBorder p-4 text-sm">
          <h2 className="text-base font-bold">ملخص الجولة الأخيرة</h2>
          <p>اتحلّل {summary.analyzed} · نفس البيانات {summary.unchanged} · فرص للمراجعة {summary.opportunities} · محجوبة {summary.blocked} · المدة {summary.duration_seconds} ثانية · رموز OpenAI المستخدمة {summary.ai_tokens}</p>
          <p>بيانات غير متاحة ({summary.unavailable.length}) {summary.unavailable.slice(0, 30).join("، ")}</p>
          {summary.unscanned.length > 0 && <p>خارج حد الجولة ({summary.unscanned.length}) {summary.unscanned.slice(0, 20).join("، ")}</p>}
          {summary.notice && <p className="text-amber-300">{messages[summary.notice] ?? summary.notice}</p>}
          {summary.provider_error && <p className="text-amber-300">{messages[summary.provider_error] ?? summary.provider_error}</p>}
        </div>}
      </>}
      <label className="block text-sm">سجل الجولات
        <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value ? Number(e.target.value) : undefined)} className="ms-2 max-w-full rounded-lg border border-surfaceBorder bg-surface p-2">
          <option value="">آخر جولة للإعدادات الحالية</option>
          {jobs.map((job) => <option key={job.id} value={job.id}>#{job.id} · {modes[job.mode]} · {states[job.status]} · {job.session} · محاولات {job.attempts}</option>)}
        </select>
      </label>
      <ScannerResults key={selected ?? "latest"} jobId={selected} refresh={jobs[0]?.status === "RUNNING" ? 0 : (jobs[0]?.id ?? 0) * 2 + refresh} />
    </section>
  );
}
