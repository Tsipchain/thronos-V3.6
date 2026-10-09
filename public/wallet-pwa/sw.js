const CACHE = 'thr-wallet-pwa-v4';

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


// ── 3FA Push Notifications ─────────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) { return; }

  if (data.type === '3fa_approval') {
    const action = data.action || 'transaction';
    const details = data.details || {};
    const amount = details.amount ? ` ${details.amount} THR` : '';
    const to = details.to ? ` → ${details.to.slice(0, 12)}...` : '';

    e.waitUntil(
      self.registration.showNotification('Thronos — Approve Transaction', {
        body: `${action}${amount}${to}\nTap to approve or deny.`,
        icon: '/static/img/thronos-token.png',
        badge: '/static/img/thronos-token.png',
        tag: `3fa-${data.approval_id}`,
        requireInteraction: true,
        data: data,
        actions: [
          { action: 'approve', title: 'Approve' },
          { action: 'deny', title: 'Deny' },
        ],
      })
    );
  }
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const data = e.notification.data || {};

  if (data.type === '3fa_approval') {
    e.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
        const payload = {
          type: '3fa_action',
          approval_id: data.approval_id,
          user_action: e.action || 'open',
          details: data.details,
        };
        if (clients.length > 0) {
          clients[0].postMessage(payload);
          clients[0].focus();
        } else {
          self.clients.openWindow(`/wallet-pwa/?3fa=${data.approval_id}&action=${e.action || 'open'}`);
        }
      })
    );
  }
});
