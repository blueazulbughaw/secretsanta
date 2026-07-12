const CACHE = "giftcircle-v1";
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

  // Cache-first for the shell & static assets
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit ||
      fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match("/"))
    )
  );
});

// Future-ready: push handler (activates once Web Push sending ships server-side)
self.addEventListener("push", (e) => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(data.title || "GiftCircle", {
    body: data.body || "",
    icon: "/static/icon-192.png",
    data: { link: data.link_path || "/" },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(clients.openWindow("/#" + (e.notification.data.link || "/")));
});
