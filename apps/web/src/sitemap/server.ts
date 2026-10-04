import { SITEMAP_TIMEOUT_MS, serverApiOrigin, serverSiteOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';
import { indexXml, urlsetXml } from './xml';

type Section = components['schemas']['Section'];

/*
 * What `/sitemap.xml` and `/sitemaps/<section>-<page>.xml` answer. The API
 * lists the pages; when it cannot, the answer is 503, never an empty sitemap
 * (a crawler would read that as "everything was removed").
 */

const XML = 'application/xml; charset=utf-8';
// The API's own lifetime of the same lists: a published page is in the next crawl.
const CACHE = 'public, max-age=300';
const RETRY_SECONDS = 60;

const CHILD = /^([a-z]+)-(\d{1,9})\.xml$/;

function ok(body: string): Response {
  return new Response(body, { headers: { 'Content-Type': XML, 'Cache-Control': CACHE } });
}

function unavailable(): Response {
  return new Response('Sitemap unavailable', {
    status: 503,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'Retry-After': String(RETRY_SECONDS),
    },
  });
}

function missing(): Response {
  return new Response('Not found', { status: 404, headers: { 'Cache-Control': 'no-store' } });
}

function client() {
  return createApiClient({ baseUrl: serverApiOrigin() });
}

const timeout = () => AbortSignal.timeout(SITEMAP_TIMEOUT_MS);

export async function sitemapIndexResponse(): Promise<Response> {
  const result = await attempt(client().GET('/sitemap', { signal: timeout() }));
  return result.ok ? ok(indexXml(result.data, serverSiteOrigin())) : unavailable();
}

export async function sitemapChildResponse(file: string): Promise<Response> {
  const match = CHILD.exec(file);
  if (match === null) {
    return missing();
  }
  const result = await attempt(
    client().GET('/sitemap/{section}', {
      params: {
        path: { section: match[1] as Section },
        query: { page: Number(match[2]) },
      },
      signal: timeout(),
    })
  );
  if (result.ok) {
    return ok(urlsetXml(result.data, serverSiteOrigin()));
  }
  // An unknown section is a 422 and a switched-off one a 404: neither is a sitemap.
  return result.status === 404 || result.status === 422 ? missing() : unavailable();
}
