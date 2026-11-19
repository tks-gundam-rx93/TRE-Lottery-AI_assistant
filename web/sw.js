'use strict';
const CACHE = 'tre-haro-pwa-v1';
const SHELL = ['/', '/pwa.js', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/maskable-512.png', '/icons/apple-touch-icon.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith('tre-haro-pwa-') && key !== CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'ACTIVATE_UPDATE') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  // APIs, uploaded CSV, predictions and third-party resources never enter CacheStorage.
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  const navigation = request.mode === 'navigate' && url.pathname === '/';
  if (!navigation && !SHELL.includes(url.pathname)) return;
  const cacheKey = navigation ? '/' : url.pathname;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(request);
      if (response.ok && response.type !== 'opaque') await cache.put(cacheKey, response.clone());
      // While a free server is waking up, retain the installed shell on a 503.
      if (!response.ok) return (await cache.match(cacheKey)) || response;
      return response;
    } catch {
      return (await cache.match(cacheKey)) || new Response('オフラインです。一度オンラインで開いてから再試行してください。',
        {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}});
    }
  })());
});
