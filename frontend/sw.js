/* RouteNex service worker. Bump VERSION whenever app files change.
   - App shell: network-first (updates apply immediately), cache fallback when offline.
   - Leaflet + map tiles: cache-first (so a visited map still draws offline).
   - /api/*: NEVER cached (authenticated, live data). Offline -> clean JSON error. */
const VERSION = 'v5';
const SHELL = `routenex-shell-${VERSION}`, MAPS = `routenex-maps-${VERSION}`;
const PRECACHE = ['/', '/static/styles.css', '/static/app.js', '/static/pwa.js', '/static/phase2.js', '/static/phase3.js', '/static/phase4.js', '/static/phase5.js', '/manifest.webmanifest',
  '/static/icons/icon-192.png', '/static/icons/icon-512.png'];
const MAP_HOSTS = ['unpkg.com', 'tile.openstreetmap.org'];
const MAX_MAP_ENTRIES = 250;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => ![SHELL, MAPS].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

async function trim(cacheName, max) {
  const c = await caches.open(cacheName), keys = await c.keys();
  if (keys.length > max) await Promise.all(keys.slice(0, keys.length - max).map(k => c.delete(k)));
}

self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET') return;

  if (url.origin === location.origin && url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(req).catch(() => new Response(JSON.stringify({ detail: 'You are offline. Reconnect to continue.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } })));
    return;
  }
  if (MAP_HOSTS.some(h => url.hostname === h || url.hostname.endsWith('.' + h))) {
    e.respondWith(caches.open(MAPS).then(async c => {
      const hit = await c.match(req); if (hit) return hit;
      try {
        // CORS fetch -> real, small, cacheable response (an opaque one would cost ~7 MB of storage quota each)
        const res = await fetch(req.url, { mode: 'cors', credentials: 'omit' });
        if (res.ok) { c.put(req, res.clone()); trim(MAPS, MAX_MAP_ENTRIES); }
        return res;
      } catch (err) { return Response.error(); }
    }));
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(fetch(req).then(res => {
      if (res.ok && (req.mode === 'navigate' || url.pathname.startsWith('/static/'))) { const copy = res.clone(); caches.open(SHELL).then(c => c.put(req.mode === 'navigate' ? '/' : req, copy)); }
      return res;
    }).catch(async () => (await caches.match(req)) || (req.mode === 'navigate' ? caches.match('/') : Response.error())));
  }
});
