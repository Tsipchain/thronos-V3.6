const CACHE = 'thr-wallet-pwa-v1';

const PRECACHE = [
  '/wallet-pwa/',
  '/wallet-pwa/index.html',
  '/wallet-pwa/app.js',
  '/wallet-pwa/app.css',
  '/wallet-pwa/manifest.json',
  '/static/img/thronos-token.png'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Never cache API calls
  if (url.pathname.startsWith('/pwa-api/') || url.pathname.startsWith('/api/')) return;

  // Cache-first for app shell; network-first for everything else
  if (PRECACHE.includes(url.pathname)) {
    e.respondWith(
      caches.match(request).then(r => r || fetch(request).then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(request, clone));
        return res;
      }))
    );
    return;
  }

  // Network-first with cache fallback for other resources
  e.respondWith(
    fetch(request).then(res => {
      if (res.ok) {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(request, clone));
      }
      return res;
    }).catch(() => caches.match(request))
  );
});
