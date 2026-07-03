/* ═══════════════════════════════════════════════
   Vidyarthi Mitra E-Paper — Service Worker (kill switch)
   The previous cache-first worker trapped users on stale JS/CSS.
   This version caches nothing: it deletes all caches, unregisters
   itself, and reloads open pages so everyone gets the latest code.
   ═══════════════════════════════════════════════ */

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (e) { /* ignore */ }
    try {
      await self.registration.unregister();
    } catch (e) { /* ignore */ }
    try {
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => { try { c.navigate(c.url); } catch (e) { /* ignore */ } });
    } catch (e) { /* ignore */ }
  })());
});

// No fetch handler on purpose — all requests go straight to the network.
