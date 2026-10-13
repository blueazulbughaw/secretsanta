const CACHE = "giftcircle-v3";
const STATIC = [
  "/",
  "/static/css/app.css",
  "/static/js/api.js",
  "/static/js/app.js",
  "/static/manifest.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  if (url.pathname.startsWith("/api/")) {
    // Network-first for data
    e.respondWith(
      fetch(e.request).catch(() =>
        new Response(JSON.stringify({ error: "You're offline. Please reconnect and try again." }),
          { status: 503, headers: { "Content-Type": "application/json" } })
      )
    );
    return;
  }

  // Network-first for the shell & static assets, so deploys show up on the next
  // reload instead of being masked by a stale cache; cache is just the offline fallback.
  e.respondWith(
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match("/")))
  );
});

// Web Push (sent by services/push_service.py): show it like the app's bell would
self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) {}
  e.waitUntil(self.registration.showNotification(data.title || "Secret Santa", {
    body: data.body || "",
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    tag: data.id ? `n${data.id}` : undefined,
    data: { link: data.link_path || "/", id: data.id || null },
  }));
});
// Tapping it opens what it's about (reusing an open Secret Santa tab if there is one) and
// marks it read in the bell.
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const { link, id } = e.notification.data || {};
  const url = new URL("/#" + (link || "/"), self.location.origin).href;
  e.waitUntil((async () => {
    if (id) fetch(`/api/notifications/${id}/read`, { method: "POST", credentials: "include" }).catch(() => {});
    const open = await clients.matchAll({ type: "window", includeUncontrolled: true });
    const tab = open.find((c) => new URL(c.url).origin === self.location.origin);
    if (tab) { await tab.focus(); return tab.navigate ? tab.navigate(url) : undefined; }
    return clients.openWindow(url);
  })());
});
