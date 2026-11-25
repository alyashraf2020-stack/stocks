/* Only these immutable public, credential-free shell contents can be stored. */
const VERSION = "egx-offline-v2";
const SHELL = ["/pwa/offline.html", "/pwa/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(VERSION);
    for (const path of SHELL) {
      const response = await fetch(path, { cache: "reload", redirect: "error", credentials: "same-origin" });
      if (!response.ok || /(?:private|no-store)/i.test(response.headers.get("Cache-Control") || "")) {
        throw new Error("Public offline shell unavailable");
      }
      await cache.put(path, response);
    }
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith("egx-offline-") && key !== VERSION) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data === "EGX_APPLY_UPDATE") event.waitUntil(self.skipWaiting());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (SHELL.includes(url.pathname) && !url.search) {
    event.respondWith(caches.open(VERSION).then(async (cache) => (await cache.match(url.pathname)) || fetch(event.request)));
  } else if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request, { cache: "no-store" }).catch(async () => {
      const shell = await (await caches.open(VERSION)).match(SHELL[0]);
      return shell || new Response("الاتصال مش متاح. بيانات السوق الحالية غير متاحة.", {
        status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
      });
    }));
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data?.json() || {}; } catch { /* Always show a privacy-safe fallback. */ }
  const title = typeof data.title === "string" ? data.title.slice(0, 100) : "EGX · إشعار جديد";
  const body = typeof data.body === "string" ? data.body.slice(0, 360) : "افتح التطبيق الخاص بيك للمراجعة.";
  event.waitUntil(self.registration.showNotification(title, {
    body, icon: "/pwa/icon-192.png", dir: "rtl", lang: "ar-EG",
    tag: /^[a-f0-9]{12,64}$/.test(data.tag ?? "") ? data.tag : "egx-notification",
    data: {path: data.path === "/orders/proposals" ? "/orders/proposals" : "/notifications"},
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const path = event.notification.data?.path === "/orders/proposals" ? "/orders/proposals" : "/notifications";
    const target = new URL(path, self.location.origin).href;
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (client.url === target && client.focus) return client.focus();
    }
    return self.clients.openWindow(target);
  })());
});
