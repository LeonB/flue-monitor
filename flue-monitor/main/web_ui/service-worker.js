// Cache only the public, self-contained connecting screen. Dashboard HTML,
// authentication responses and sensor/API data always come from the device.
const CACHE = 'flue-startup-__STARTUP_VERSION__';
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const response = await fetch('/loading.html', {cache: 'reload'});
    if (!response.ok || !(response.headers.get('Content-Type') || '').includes('text/html'))
      throw new Error('Loading screen unavailable');
    await cache.put('/loading.html', response);
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys())
      if (name.startsWith('flue-startup-') && name !== CACHE) await caches.delete(name);
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || event.request.mode !== 'navigate' ||
      url.origin !== self.location.origin || url.pathname !== '/') return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    return await cache.match('/loading.html') || fetch(event.request);
  })());
});
