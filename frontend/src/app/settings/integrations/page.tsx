"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Link2, ShieldCheck, RefreshCw } from "lucide-react";
import {
  Connection,
  dateLabel,
  errorMessage,
  freshnessLabel,
  stateLabels,
  thndr,
  toolLabels,
} from "@/lib/thndr";

export default function IntegrationsPage() {
  const [data, setData] = useState<Connection | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    thndr<Connection>("status", "GET", controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, []);
  async function action(kind: "connect" | "disconnect" | "sync" | "status") {
    setBusy(true);
    setError("");
    try {
      if (kind === "connect") {
        const { authorization_url } = await thndr<{
          authorization_url: string;
        }>("connect", "POST");
        if (new URL(authorization_url).origin !== "https://prod.thndr.app")
          throw new Error(errorMessage("INVALID_METADATA"));
        window.location.assign(authorization_url);
        return;
      }
      if (kind !== "status") await thndr(kind, "POST");
      setData(await thndr<Connection>("status"));
    } catch (e) {
      setError(e instanceof Error ? e.message : errorMessage(""));
      try {
        setData(await thndr<Connection>("status"));
      } catch {
        /* Preserve the original error. */
      }
    } finally {
      setBusy(false);
    }
  }
  const connected = data?.status === "CONNECTED";
  const disconnectable =
    data && !["NOT_CONFIGURED", "DISCONNECTED"].includes(data.status);
  return (
    <section dir="rtl" className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1 className="text-2xl sm:text-3xl font-bold">ربط الحسابات</h1>
        <p className="mt-2 text-gray-400">
          إدارة وصول التطبيق لمحفظتك في ثاندر.
        </p>
      </header>
      <article className="rounded-2xl border border-surfaceBorder bg-surface p-5 sm:p-7 space-y-5">
        <div className="flex items-center gap-3">
          <Link2 aria-hidden className="text-primary" />
          <h2 className="text-xl font-bold">ثاندر</h2>
        </div>
        <div aria-live="polite" className="flex items-center gap-2">
          <ShieldCheck size={18} />
          {data
            ? stateLabels[data.status]
            : busy
              ? "جاري فحص الاتصال…"
              : "حالة الاتصال غير متاحة"}
        </div>
        <p className="text-sm text-gray-400">
          اختار أدوات القراءة عند تسجيل الدخول في ثاندر. الموافقة بتتم من
          موبايلك.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-lg bg-primary text-background font-bold px-4 py-2 disabled:opacity-40"
            disabled={
              busy ||
              !data ||
              !["DISCONNECTED", "AUTHORIZING"].includes(data.status)
            }
            onClick={() => action("connect")}
          >
            ربط ثاندر
          </button>
          <button
            className="rounded-lg border border-surfaceBorder px-4 py-2 disabled:opacity-40"
            disabled={busy || !disconnectable}
            onClick={() => action("disconnect")}
          >
            فصل ثاندر
          </button>
          <button
            className="rounded-lg px-3 py-2 inline-flex gap-2 items-center disabled:opacity-40"
            disabled={busy}
            onClick={() => action(connected ? "sync" : "status")}
          >
            <RefreshCw size={16} />
            {connected ? "مزامنة الحساب" : "تحديث الحالة"}
          </button>
        </div>
        {(error || data?.error) && (
          <p role="alert" className="text-amber-300">
            {error || errorMessage(data!.error!)}
          </p>
        )}
        {data && (
          <dl className="grid gap-4 text-sm border-t border-surfaceBorder pt-4 sm:grid-cols-3">
            <div>
              <dt className="text-gray-400">آخر مزامنة بتوقيت القاهرة</dt>
              <dd>{dateLabel(data.last_sync)}</dd>
            </div>
            <div>
              <dt className="text-gray-400">صلاحية الحساب</dt>
              <dd>
                {data.permissions.includes("thndr:read")
                  ? "قراءة فقط"
                  : "لا توجد صلاحية مؤكدة"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-400">حالة أسعار المحفظة</dt>
              <dd>{freshnessLabel[data.freshness]}</dd>
            </div>
          </dl>
        )}
      </article>
      {data && (
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            ["الأدوات المسموح بها", data.available],
            ["الأدوات غير المتاحة", data.unavailable],
          ].map(([label, items]) => (
            <article
              key={String(label)}
              className="rounded-xl border border-surfaceBorder p-5"
            >
              <h2 className="font-bold mb-3">{label}</h2>
              <ul className="space-y-1 text-sm text-gray-300">
                {(items as string[]).map((id) => (
                  <li key={id}>{toolLabels[id] || id}</li>
                ))}
              </ul>
              {items.length === 0 && (
                <p className="text-gray-400">لا توجد أدوات في القائمة</p>
              )}
            </article>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-5 text-primary underline">
        <Link href="/portfolio">عرض المحفظة</Link>
        <a
          href="https://docs.thndr.app/clients/chatgpt"
          target="_blank"
          rel="noreferrer"
        >
          دليل الربط الرسمي مع ChatGPT
        </a>
      </div>
    </section>
  );
}
