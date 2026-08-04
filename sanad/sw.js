// Sanad service worker — offline-after-first-visit for clinicians whose
// network comes and goes. Strategy: serve from cache immediately (the page
// must open with the network gone), refresh the cache in the background so
// the next open picks up a newer deploy (stale-while-revalidate).
const C = 'sanad-v4';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(C).then(c => c.addAll(['./'])).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('sanad-') && k !== C).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.match(e.request).then(hit => {
    const refresh = fetch(e.request).then(res => {
      if (res.ok) { const cp = res.clone(); caches.open(C).then(c => c.put(e.request, cp)); }
      return res;
    }).catch(() => hit || caches.match('./'));
    return hit || refresh;
  }));
});
