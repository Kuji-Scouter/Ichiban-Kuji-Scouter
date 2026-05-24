const VERSION = 'kuji-v2';
const SHELL = `${VERSION}-shell`;

const PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './logo.png',
  './data/raw-sets.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(SHELL)
      .then((c) => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

function networkFirst(req) {
  return fetch(req).then((resp) => {
    if (resp && resp.ok) {
      const copy = resp.clone();
      caches.open(SHELL).then((c) => c.put(req, copy));
    }
    return resp;
  }).catch(() => caches.match(req));
}

function cacheFirst(req) {
  return caches.match(req).then((cached) =>
    cached || fetch(req).then((resp) => {
      if (resp && resp.ok) {
        const copy = resp.clone();
        caches.open(SHELL).then((c) => c.put(req, copy));
      }
      return resp;
    })
  );
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  const isFreshAsset =
    req.mode === 'navigate' ||
    url.pathname.endsWith('.html') ||
    url.pathname.endsWith('/data/ebay-prices.json');

  e.respondWith(isFreshAsset ? networkFirst(req) : cacheFirst(req));
});
