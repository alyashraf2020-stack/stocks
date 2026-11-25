"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{outcome: string}>;
}

export default function PwaControl() {
  const [offline, setOffline] = useState(false);
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  const [install, setInstall] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    const connectivity = () => {
      setOffline(!navigator.onLine);
      document.documentElement.toggleAttribute("data-egx-offline", !navigator.onLine);
    };
    const show = (event: Event) => {
      event.preventDefault(); setInstall(event as InstallPrompt);
    };
    const installed = () => setInstall(null);
    connectivity();
    window.addEventListener("online", connectivity);
    window.addEventListener("offline", connectivity);
    window.addEventListener("beforeinstallprompt", show);
    window.addEventListener("appinstalled", installed);
    let mounted = true;
    let timer: (() => void) | undefined;
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then((registration) => {
        if (!mounted) return;
        if (registration.waiting) setWaiting(registration.waiting);
        registration.addEventListener("updatefound", () => {
          const worker = registration.installing;
          worker?.addEventListener("statechange", () => {
            if (mounted && worker?.state === "installed" && navigator.serviceWorker.controller) setWaiting(worker);
          });
        });
        timer = () => { if (!document.hidden) void registration.update().catch(() => {}); };
        document.addEventListener("visibilitychange", timer);
      }).catch(() => {});
    }
    return () => {
      mounted = false;
      document.documentElement.removeAttribute("data-egx-offline");
      if (timer) document.removeEventListener("visibilitychange", timer);
      window.removeEventListener("online", connectivity);
      window.removeEventListener("offline", connectivity);
      window.removeEventListener("beforeinstallprompt", show);
      window.removeEventListener("appinstalled", installed);
    };
  }, []);

  async function installApp() {
    if (!install) return;
    await install.prompt();
    await install.userChoice;
    setInstall(null);
  }

  return <div className="mx-auto w-full max-w-7xl px-4 text-sm">
    {offline && <p role="status" className="my-2 rounded-lg border border-amber-400/40 bg-surface p-3 text-amber-300">الاتصال مش متاح. بيانات السوق الحالية غير متاحة.</p>}
    {(waiting || install) && <div className="my-2 flex flex-wrap items-center gap-2">
      {waiting && <button className="rounded-lg border border-primary px-3 py-2 text-primary" onClick={() => {
        navigator.serviceWorker.addEventListener("controllerchange", () => window.location.reload(), {once: true});
        waiting.postMessage("EGX_APPLY_UPDATE");
      }}>في تحديث جاهز · أعد التحميل</button>}
      {install && <button className="rounded-lg bg-primary px-3 py-2 font-bold text-background" onClick={() => void installApp()}>ثبّت التطبيق</button>}
      <Link href="/settings/system" className="p-2 text-primary underline">تعليمات التثبيت</Link>
    </div>}
  </div>;
}
