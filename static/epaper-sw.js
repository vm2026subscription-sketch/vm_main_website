/* ═══════════════════════════════════════════════
   Vidyarthi Mitra E-Paper — Service Worker
   PWA Offline Support + Cache Strategy
   ═══════════════════════════════════════════════ */

const CACHE_NAME = 'vm-epaper-v4';
const PRECACHE_URLS = [
  '/epaper-viewer',
  '/static/epaper-viewer.css',
  '/static/epaper-viewer.js',
  '/static/logo.png',
  '/static/title.png',
];

// Install — precache essential assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Precaching app shell');
      return cache.addAll(PRECACHE_URLS);
    })
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch — network-first for API, cache-first for assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET
  if (event.request.method !== 'GET') return;

  // API calls — network first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets — network first (so new deploys load immediately), fall back
  // to cache only when offline. Cache-first used to trap users on old JS/CSS.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Pages — network first
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return res;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // Offline fallback
          return caches.match('/epaper-viewer');
        })
      )
  );
});

// Push Notifications
self.addEventListener('push', (event) => {
  let data = { title: 'Vidyarthi Mitra', body: 'New E-Paper edition available!' };
  try {
    data = event.data.json();
  } catch (e) {
    data.body = event.data?.text() || data.body;
  }

  event.waitUntil(
    self.registration.showNotification(data.title || 'Vidyarthi Mitra E-Paper', {
      body: data.body,
      icon: '/static/title.png',
      badge: '/static/title.png',
      tag: 'epaper-new-edition',
      data: { url: data.url || '/epaper-viewer' },
      actions: [{ action: 'open', title: 'Read Now' }],
    })
  );
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/epaper-viewer';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes('epaper') && 'focus' in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});
