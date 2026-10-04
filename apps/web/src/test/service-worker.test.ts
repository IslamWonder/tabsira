// @vitest-environment node
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

/*
 * public/sw.js runs in a service worker, not in the bundle, so it is loaded
 * here into a sandbox with a fake cache store and network.
 */

const SOURCE = readFileSync(path.resolve(__dirname, '../../public/sw.js'), 'utf8');
const ORIGIN = 'https://tabsira.test';

type Listener = (event: FakeEvent) => void;

interface FakeEvent {
  request?: { url: string; method: string; mode: string };
  respondWith: (response: Promise<Response>) => void;
  waitUntil: (work: Promise<unknown>) => void;
}

interface Worker {
  routeFor: (request: { url: string; method: string; mode: string }) => string;
  assetsIn: (html: string) => string[];
}

function fakeCaches(initial: Record<string, Record<string, Response>> = {}) {
  const stores = new Map(
    Object.entries(initial).map(([name, entries]) => [name, new Map(Object.entries(entries))])
  );
  const keyOf = (request: string | { url: string }) =>
    typeof request === 'string' ? request : new URL(request.url).pathname;
  const open = async (name: string) => {
    const store = stores.get(name) ?? new Map<string, Response>();
    stores.set(name, store);
    return {
      match: async (request: string | { url: string }) => store.get(keyOf(request))?.clone(),
      put: async (request: { url: string }, response: Response) => {
        store.set(keyOf(request), response);
      },
      addAll: async (urls: string[]) => {
        for (const url of urls) {
          store.set(url, new Response(url === '/offline' ? OFFLINE_HTML : 'asset'));
        }
      },
    };
  };
  return {
    stores,
    api: {
      open,
      keys: async () => Array.from(stores.keys()),
      delete: async (name: string) => stores.delete(name),
      match: async (request: string) => {
        for (const store of stores.values()) {
          const hit = store.get(request);
          if (hit) return hit.clone();
        }
        return undefined;
      },
    },
  };
}

const OFFLINE_HTML =
  '<link href="/_next/static/css/app.css"><script src="/_next/static/chunks/main.js"></script>' +
  '<script src="/_next/static/chunks/main.js"></script>';

function load(caches = fakeCaches(), fetch = vi.fn<(request: unknown) => Promise<Response>>()) {
  const listeners: Record<string, Listener> = {};
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, listener: Listener) => {
      listeners[type] = listener;
    },
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined) },
  };
  const context = vm.createContext({
    self,
    caches: caches.api,
    fetch,
    URL,
    Response,
    Promise,
    Array,
    Set,
  });
  vm.runInContext(SOURCE, context);
  return { worker: context as unknown as Worker, listeners, self, caches, fetch };
}

function request(pathOrUrl: string, init: { method?: string; mode?: string } = {}) {
  return {
    url: new URL(pathOrUrl, ORIGIN).href,
    method: init.method ?? 'GET',
    mode: init.mode ?? 'no-cors',
  };
}

async function dispatch(listener: Listener | undefined, req?: ReturnType<typeof request>) {
  let responded: Promise<Response> | undefined;
  let waited: Promise<unknown> | undefined;
  listener?.({
    request: req,
    respondWith: (response) => {
      responded = response;
    },
    waitUntil: (work) => {
      waited = work;
    },
  });
  await waited;
  return responded === undefined ? undefined : await responded;
}

describe('the service worker routes', () => {
  const { worker } = load();

  it.each([
    ['/_next/static/chunks/app.js', 'static'],
    ['/_next/static/media/font.woff2', 'static'],
    ['/icons/icon-192.png', 'static'],
    ['/favicon.ico', 'static'],
    ['/manifest.webmanifest', 'static'],
    ['/_next/image?url=%2Fphoto.jpg&w=640&q=75', 'network'],
    ['/uploads/photo.jpg', 'network'],
    ['/api/anything', 'network'],
    ['https://api.tabsira.test/insights/1', 'network'],
    ['https://tiles.openfreemap.org/planet', 'network'],
  ])('%s → %s', (url, route) => {
    expect(worker.routeFor(request(url))).toBe(route);
  });

  it('answers page navigations itself, and never anything but GET', () => {
    expect(worker.routeFor(request('/world', { mode: 'navigate' }))).toBe('page');
    expect(worker.routeFor(request('/_next/static/a.js', { method: 'POST' }))).toBe('network');
  });

  it('reads each build file of the offline page once', () => {
    expect(worker.assetsIn(OFFLINE_HTML)).toEqual([
      '/_next/static/css/app.css',
      '/_next/static/chunks/main.js',
    ]);
    expect(worker.assetsIn('<p>no assets</p>')).toEqual([]);
  });
});

describe('the service worker lifecycle', () => {
  it('stores the offline page and what it needs on install', async () => {
    const { listeners, caches, self } = load();
    await dispatch(listeners.install);
    const store = caches.stores.get('tabsira-v1');
    expect(Array.from(store?.keys() ?? []).sort()).toEqual(
      [
        '/_next/static/chunks/main.js',
        '/_next/static/css/app.css',
        '/favicon.ico',
        '/icons/icon-192.png',
        '/manifest.webmanifest',
        '/offline',
      ].sort()
    );
    expect(self.skipWaiting).toHaveBeenCalledOnce();
  });

  it('installs even if the offline page could not be read back', async () => {
    const caches = fakeCaches();
    const open = caches.api.open;
    caches.api.open = async (name: string) => ({
      ...(await open(name)),
      match: async () => undefined,
    });
    const { listeners, self } = load(caches);
    await dispatch(listeners.install);
    expect(self.skipWaiting).toHaveBeenCalledOnce();
  });

  it('drops the caches of older releases on activate', async () => {
    const caches = fakeCaches({ 'tabsira-v0': {}, 'tabsira-v1': {} });
    const { listeners, self } = load(caches);
    await dispatch(listeners.activate);
    expect(Array.from(caches.stores.keys())).toEqual(['tabsira-v1']);
    expect(self.clients.claim).toHaveBeenCalledOnce();
  });
});

describe('the service worker answers', () => {
  it('serves a cached static file without the network', async () => {
    const caches = fakeCaches({ 'tabsira-v1': { '/icons/icon-192.png': new Response('cached') } });
    const { listeners, fetch } = load(caches);
    const response = await dispatch(listeners.fetch, request('/icons/icon-192.png'));
    expect(await response?.text()).toBe('cached');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('fetches and keeps a static file it does not have, but not a failed one', async () => {
    const { listeners, fetch, caches } = load();
    fetch
      .mockResolvedValueOnce(new Response('fresh'))
      .mockResolvedValueOnce(new Response('gone', { status: 404 }));
    expect(await (await dispatch(listeners.fetch, request('/_next/static/a.js')))?.text()).toBe(
      'fresh'
    );
    await dispatch(listeners.fetch, request('/_next/static/b.js'));
    const store = caches.stores.get('tabsira-v1');
    expect(store?.has('/_next/static/a.js')).toBe(true);
    expect(store?.has('/_next/static/b.js')).toBe(false);
  });

  it('goes to the network for pages and shows /offline when it cannot', async () => {
    const caches = fakeCaches({ 'tabsira-v1': { '/offline': new Response('offline page') } });
    const { listeners, fetch } = load(caches);
    fetch
      .mockResolvedValueOnce(new Response('live page'))
      .mockRejectedValueOnce(new TypeError('offline'));
    expect(
      await (await dispatch(listeners.fetch, request('/world', { mode: 'navigate' })))?.text()
    ).toBe('live page');
    expect(
      await (await dispatch(listeners.fetch, request('/world', { mode: 'navigate' })))?.text()
    ).toBe('offline page');
    expect(caches.stores.get('tabsira-v1')?.has('/world')).toBe(false);
  });

  it('returns a network error when even /offline is missing', async () => {
    const { listeners, fetch } = load();
    fetch.mockRejectedValueOnce(new TypeError('offline'));
    const response = await dispatch(listeners.fetch, request('/me', { mode: 'navigate' }));
    expect(response?.type).toBe('error');
  });

  it('leaves API calls and photos alone', async () => {
    const { listeners, fetch } = load();
    expect(
      await dispatch(listeners.fetch, request('https://api.tabsira.test/world'))
    ).toBeUndefined();
    expect(await dispatch(listeners.fetch, request('/_next/image?url=x'))).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
  });
});
