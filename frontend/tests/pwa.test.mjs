import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../public/sw.js", import.meta.url), "utf8");
const manifest = JSON.parse(await readFile(new URL("../public/manifest.webmanifest", import.meta.url)));

function harness({ header = "public", failed = false } = {}) {
  const origin = "https://egx.example";
  const events = new Map();
  const data = new Map([
    ["egx-offline-old", new Map()],
    ["another-app", new Map()],
  ]);
  const request = [];
  const navigations = [];
  const hooks = {};
  const scope = {
    self: {
      addEventListener: (type, cb) => events.set(type, cb),
      location: {origin},
      skipWaiting: async () => { hooks.updated = true; },
      clients: {
        claim: async () => { hooks.claimed = true; },
        matchAll: async () => [],
        openWindow: async (url) => navigations.push(url),
      },
      registration: {showNotification: async () => {}},
    },
    fetch: async (path) => {
      request.push(typeof path === "string" ? path : path.url);
      if (failed) throw new Error("Offline");
      return new Response(path, {headers: {"Cache-Control": header}});
    },
    caches: {
      open: async (key) => {
        if (!data.has(key)) data.set(key, new Map());
        return {put: async (path, response) => data.get(key).set(path, response),
                match: async (path) => data.get(key).get(path)};
      },
      keys: async () => [...data.keys()],
      delete: async (key) => data.delete(key),
    },
    URL, Response,
  };
  vm.runInNewContext(source, scope);
  function fire(type, args = {}) {
    let promise;
    events.get(type)({waitUntil: (p) => {promise = p;}, respondWith: (p) => {promise = p;}, ...args});
    return promise;
  }
  return {fire, scope, request, hooks, data, navigations, origin};
}

test("Arabic, same-origin standalone manifest and real PNG icon dimensions", async () => {
  assert.equal(manifest.dir, "rtl");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.scope, "/");
  assert.equal(manifest.start_url, "/");
  for (const icon of manifest.icons) {
    assert.match(icon.src, /^\/pwa\//);
    const blob = await readFile(new URL("../public" + icon.src, import.meta.url));
    assert.equal(blob.subarray(1,4).toString(), "PNG");
    assert.equal(blob.readUInt32BE(16) + "x" + blob.readUInt32BE(20), icon.sizes);
  }
});

test("only the public offline shell is put in storage", async () => {
  const {fire, data, request} = harness();
  await fire("install");
  assert.deepEqual(request, ["/pwa/offline.html", "/pwa/icon-192.png"]);
  assert.deepEqual([...data.get("egx-offline-v2").keys()], request);
  assert.equal(fire("fetch", {request: {method: "GET", url: "https://egx.example/api/v1/portfolio"}}), undefined);
  assert.equal(fire("fetch", {request: {method: "POST", url: "https://egx.example/system"}}), undefined);
  await fire("fetch", {request: {method: "GET", mode: "navigate", url: "https://egx.example/portfolio"}});
  assert.deepEqual([...data.get("egx-offline-v2").keys()], ["/pwa/offline.html", "/pwa/icon-192.png"]);
});

test("reject private cache headers; selective update and blank offline shell", async () => {
  const bad = harness({header: "private,no-store"});
  await assert.rejects(bad.fire("install"), /Public offline shell unavailable/);

  const {fire, data, scope, hooks} = harness();
  await fire("install");
  assert.equal(hooks.updated, undefined);
  await fire("message", {data: "EGX_APPLY_UPDATE"});
  await fire("activate");
  assert.equal(hooks.updated, true);
  assert.equal(hooks.claimed, true);
  assert.equal(data.has("egx-offline-old"), false);
  assert.equal(data.has("another-app"), true);
  scope.fetch = async () => { throw new Error("offline"); };
  const reply = await fire("fetch", {request: {method: "GET", mode: "navigate", url: "https://egx.example/portfolio"}});
  assert.equal(await reply.text(), "/pwa/offline.html");
});

test("click only opens the protected same-origin notification view", async () => {
  const {fire, navigations} = harness();
  await fire("notificationclick", {notification: {close() {}, data: {url: "https://untrusted.example"}}});
  assert.deepEqual(navigations, ["https://egx.example/notifications"]);
});


test("the proposal alert destination is also fixed and same-origin", async () => {
  const {fire, navigations} = harness();
  await fire("notificationclick", {notification: {close() {}, data: {path: "/orders/proposals"}}});
  await fire("notificationclick", {notification: {close() {}, data: {path: "//example.org/orders/proposals"}}});
  assert.deepEqual(navigations, ["https://egx.example/orders/proposals", "https://egx.example/notifications"]);
});
