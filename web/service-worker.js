/* TRE-Lottery PWA: app shell only. Do not cache draw histories or prediction responses. */
'use strict';

const APP_SHELL_CACHE = 'tre-lottery-shell-20261120-v2';
const STATIC_SHELL = [
  '/',
  '/offline.html',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-512.png',
  '/icons/apple-touch-icon.png',
  '/assets/haro-idle.webp',
  '/assets/dream_loto_loading.css',
  '/assets/dream_loto_loading.js',
  '/assets/algorithm_loading.css',
  '/assets/algorithm_loading.js'
];

self.addEventListener('install', event => {
  // Prevent one unavailable optional asset from making the whole SW install fail.
  event.waitUntil(
    caches.open(APP_SHELL_CACHE)
      .then(cache => Promise.allSettled(STATIC_SHELL.map(url => cache.add(url))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(names
        .filter(name => name.startsWith('tre-lottery-shell-') && name !== APP_SHELL_CACHE)
        .map(name => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // NEVER cache API results, user-uploaded CSV, LLM responses, or DB state.
  // Online-only requests fail naturally; the UI handles an offline API error.
  if (url.pathname.startsWith('/api/')) return;

  if (event.request.mode === 'navigate') {
    // Fetch the latest page when online; reuse last known shell when offline.
    event.respondWith(
      fetch(event.request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(caches.open(APP_SHELL_CACHE)
            .then(cache => cache.put('/', copy)));
        }
        return response;
      }).catch(async () => {
        const cache = await caches.open(APP_SHELL_CACHE);
        return (await cache.match('/')) || (await cache.match('/offline.html')) ||
          Response.error();
      })
    );
    return;
  }

  // Cache only static application assets; other requests pass through network.
  if (url.pathname.startsWith('/assets/') ||
      url.pathname.startsWith('/icons/') ||
      url.pathname === '/manifest.webmanifest' ||
      url.pathname === '/offline.html') {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok && response.type === 'basic') {
            const copy = response.clone();
            event.waitUntil(caches.open(APP_SHELL_CACHE)
              .then(cache => cache.put(event.request, copy)));
          }
          return response;
        });
      })
    );
  }
});
