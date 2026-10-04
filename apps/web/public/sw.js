/*
 * TABSIRA service worker.
 *
 * Caches static assets only: the hashed build files, the fonts and the app
 * icons, plus one page, /offline, shown when a navigation fails. It never
 * caches a page, an API response or a photo: pages and answers can be
 * personal, and photos stay under the owner's control (master prompt §19).
 * Requests to another origin (the API, map tiles) are never touched.
 *
 * Bump VERSION to drop every cache of the previous release.
 */
const VERSION = 'tabsira-v2';
const OFFLINE_URL = '/offline';
const PRECACHE = [OFFLINE_URL, '/manifest.webmanifest', '/icons/icon-192.png', '/favicon.ico'];

/** Same-origin static files whose name changes when their content does, or that never change. */
function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname === '/favicon.ico' ||
    url.pathname === '/manifest.webmanifest'
  );
}

/** What the worker answers itself; everything else goes to the network untouched. */
function routeFor(request) {
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return 'network';
  }
  if (request.mode === 'navigate') {
    return 'page';
  }
  return isStaticAsset(url) ? 'static' : 'network';
}

/** The build files the offline page needs, read from its HTML so it can show styled. */
function assetsIn(html) {
  const found = html.match(/\/_next\/static\/[^"'\s)]+/g) || [];
  return Array.from(new Set(found));
}

async function precache() {
  const cache = await caches.open(VERSION);
  await cache.addAll(PRECACHE);
  const offline = await cache.match(OFFLINE_URL);
  if (offline) {
    await cache.addAll(assetsIn(await offline.text()));
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}

async function pageOrOffline(request) {
  try {
    return await fetch(request);
  } catch {
    const offline = await caches.match(OFFLINE_URL);
    return offline || Response.error();
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const route = routeFor(event.request);
  if (route === 'static') {
    event.respondWith(cacheFirst(event.request));
  } else if (route === 'page') {
    event.respondWith(pageOrOffline(event.request));
  }
});
