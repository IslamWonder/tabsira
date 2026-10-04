import { describe, expect, it, vi } from 'vitest';
import { GET as indexRoute } from '@/app/sitemap.xml/route';
import { GET as childRoute } from '@/app/sitemaps/[file]/route';
import { serverSiteOrigin } from '@/config/server-env';
import { mockApi } from '@/test/api';
import { childPath, indexXml, urlsetXml } from './xml';

const ORIGIN = new URL('https://tabsira.me');

const INDEX = {
  page_size: 10000,
  sections: {
    static: [{ page: 0, lastmod: '2026-10-04T00:00:00Z' }],
    posts: [{ page: 0 }, { page: 1, lastmod: null }],
    places: [],
  },
};

function child(file: string) {
  return childRoute(new Request('https://tabsira.me/sitemaps/x'), {
    params: Promise.resolve({ file }),
  });
}

describe('the sitemap XML', () => {
  it('names each child by section and page, with the origin of the site', () => {
    expect(childPath('posts', 3)).toBe('/sitemaps/posts-3.xml');
    const xml = indexXml(INDEX, ORIGIN);
    expect(xml).toContain('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
    expect(xml).toContain(
      '<sitemap><loc>https://tabsira.me/sitemaps/static-0.xml</loc><lastmod>2026-10-04T00:00:00Z</lastmod></sitemap>'
    );
    expect(xml).toContain('<sitemap><loc>https://tabsira.me/sitemaps/posts-0.xml</loc></sitemap>');
    expect(xml).toContain('<sitemap><loc>https://tabsira.me/sitemaps/posts-1.xml</loc></sitemap>');
    expect(xml).not.toContain('places');
  });

  it('lists absolute urls with their date and pictures, escaped', () => {
    const xml = urlsetXml(
      [
        { path: '/' },
        { path: '/terms', lastmod: '2026-10-04T00:00:00Z', images: [] },
        { path: '/p/a&b', images: ['https://img.tabsira.me/a.jpg?x=1&y=<2>'] },
      ],
      ORIGIN
    );
    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
    expect(xml).toContain('<url><loc>https://tabsira.me/</loc></url>');
    expect(xml).toContain(
      '<url><loc>https://tabsira.me/terms</loc><lastmod>2026-10-04T00:00:00Z</lastmod></url>'
    );
    expect(xml).toContain(
      '<loc>https://tabsira.me/p/a&amp;b</loc><image:image><image:loc>https://img.tabsira.me/a.jpg?x=1&amp;y=&lt;2&gt;</image:loc></image:image>'
    );
  });

  it('escapes quotes too', () => {
    expect(urlsetXml([{ path: '/x', images: ['https://a/"q"\'s'] }], ORIGIN)).toContain(
      'https://a/&quot;q&quot;&apos;s'
    );
  });
});

describe('the site origin of the sitemap', () => {
  it('is SITE_URL read when asked, not the build time one', () => {
    expect(serverSiteOrigin({ SITE_URL: ' https://tabsira.me ' }).origin).toBe(
      'https://tabsira.me'
    );
  });

  it('falls back to the build address when SITE_URL is missing or malformed', () => {
    expect(serverSiteOrigin({}).origin).toBe('https://tabsira.test');
    expect(serverSiteOrigin({ SITE_URL: 'not a url' }).origin).toBe('https://tabsira.test');
  });
});

describe('GET /sitemap.xml', () => {
  it('writes the API index, cached for a few minutes, with the SITE_URL of the moment', async () => {
    vi.stubEnv('SITE_URL', 'https://tabsira.me');
    mockApi({ 'GET /sitemap': { body: INDEX } });
    const response = await indexRoute();
    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('application/xml; charset=utf-8');
    expect(response.headers.get('cache-control')).toBe('public, max-age=300');
    expect(await response.text()).toContain('<loc>https://tabsira.me/sitemaps/static-0.xml</loc>');
  });

  it('answers 503, never an empty sitemap, when the API is down or fails', async () => {
    for (const route of ['network-error', { status: 500 }] as const) {
      mockApi({ 'GET /sitemap': route });
      const response = await indexRoute();
      expect(response.status).toBe(503);
      expect(response.headers.get('retry-after')).toBe('60');
      expect(response.headers.get('cache-control')).toBe('no-store');
      expect(await response.text()).not.toContain('<sitemapindex');
    }
  });
});

describe('GET /sitemaps/<section>-<page>.xml', () => {
  it('asks the API for that page and writes it', async () => {
    vi.stubEnv('SITE_URL', 'https://tabsira.me');
    const api = mockApi({
      'GET /sitemap/posts': { body: [{ path: '/community/p/1', lastmod: null, images: [] }] },
    });
    const response = await child('posts-2.xml');
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('public, max-age=300');
    expect(await response.text()).toContain('<loc>https://tabsira.me/community/p/1</loc>');
    expect(new URL(api.requests[0]?.url ?? '').search).toBe('?page=2');
  });

  it('is a 404 for a name that is not a child, an unknown section or a switched-off one', async () => {
    expect((await child('posts.xml')).status).toBe(404);
    expect((await child('../x-1.xml')).status).toBe(404);
    for (const status of [404, 422]) {
      mockApi({ 'GET /sitemap/journals': { status } });
      expect((await child('journals-0.xml')).status).toBe(404);
    }
  });

  it('answers 503 when the API is down or fails', async () => {
    for (const route of ['network-error', { status: 500 }] as const) {
      mockApi({ 'GET /sitemap/static': route });
      expect((await child('static-0.xml')).status).toBe(503);
    }
  });
});
