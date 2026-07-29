// Times of Palestine service worker — offline reading for unreliable connections.
// Strategy: network-first for everything on our own origin, falling back to the
// last cached copy when offline. Every page a reader visits stays readable.
const CACHE = "top-v2";
const SHELL = [
  "/", "/en/", "/ar/", "/en/about.html", "/ar/about.html",
  "/en/status.html", "/ar/status.html", "/assets/site.css", "/manifest.json"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(e.request, { ignoreSearch: true }).then(
          (hit) => hit || caches.match(url.pathname.startsWith("/ar") ? "/ar/" : "/en/")
        )
      )
  );
});
