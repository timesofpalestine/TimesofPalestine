// Times of Palestine service worker — offline reading for unreliable connections.
// Strategy: network-first for everything on our own origin, falling back to the
// last cached copy when offline. Navigations race a short timer so a flaky
// connection shows the cached page in ~3 s instead of hanging to a TCP timeout;
// the network response still wins whenever it arrives and refreshes the cache.
const CACHE = "top-v4";
const SHELL = [
  "/", "/en/", "/ar/", "/en/about.html", "/ar/about.html",
  "/en/status.html", "/ar/status.html", "/assets/site.css", "/manifest.json",
  "/fonts/NotoKufiArabic-var.woff2"
];
const MAX_PAGES = 120; // cap the runtime cache so dead story pages don't pile up

self.addEventListener("install", (e) => {
  e.waitUntil(
    // Each shell entry individually: one 404 must not kill offline support.
    caches.open(CACHE)
      .then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => trimCache())
      .then(() => self.clients.claim())
  );
});

function trimCache() {
  return caches.open(CACHE).then((c) =>
    c.keys().then((reqs) => {
      const pages = reqs.filter((r) => !SHELL.includes(new URL(r.url).pathname));
      if (pages.length <= MAX_PAGES) return;
      // Cache API keys are insertion-ordered: the front is the oldest.
      return Promise.all(pages.slice(0, pages.length - MAX_PAGES).map((r) => c.delete(r)));
    })
  );
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const fromNet = fetch(e.request)
    .then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy).then(trimCache));
      }
      return res;
    });
  const fromCache = () =>
    caches.match(e.request, { ignoreSearch: true }).then(
      (hit) => hit || caches.match(url.pathname.startsWith("/ar") ? "/ar/" : "/en/")
    );
  if (e.request.mode === "navigate") {
    // Race: cached copy after 3 s if the network is stalling — but only when
    // a cached copy exists, so a cold cache still waits for the network.
    const timed = new Promise((resolve) => {
      setTimeout(() => fromCache().then((hit) => hit && resolve(hit)), 3000);
    });
    e.respondWith(
      Promise.race([fromNet.catch(fromCache), timed]).then((r) => r || fromNet.catch(fromCache))
    );
    return;
  }
  e.respondWith(fromNet.catch(fromCache));
});
