import { cache } from 'react';
import { SERVER_API_TIMEOUT_MS, serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';
import { type PageSeo, pageMetadata } from '@/lib/seo';

export type PublicInsight = components['schemas']['PublicInsightOut'];

/** The page's address: the `path` the API gives a published insight (apps/api page_path). */
export function publicInsightPath(id: string): string {
  return `/insights/${id}`;
}

/** The share card's address (app/insights/[id]/card): a PNG that exists while the insight is public. */
export function publicInsightCardPath(id: string): string {
  return `${publicInsightPath(id)}/card`;
}

/** The name the browser gives the downloaded card; ASCII so every device keeps it. */
export function cardFileName(id: string): string {
  return `tabsira-${id}.png`;
}

/**
 * A published insight, read by the web server. Every visitor gets the same
 * answer for the same id; the API says 404 alike for unknown, unpublished and
 * withdrawn ones, and the page must not tell them apart either. The request
 * carries no cookie and is never cached, so a withdrawal shows at once.
 */
export const loadPublicInsight = cache(async (id: string): Promise<Result<PublicInsight>> => {
  const client = createApiClient({
    baseUrl: serverApiOrigin(),
    fetch: (request) => globalThis.fetch(request, { cache: 'no-store', redirect: 'error' }),
  });
  return attempt(
    client.GET('/public/insights/{insight_id}', {
      params: { path: { insight_id: id } },
      signal: AbortSignal.timeout(SERVER_API_TIMEOUT_MS),
    })
  );
});

/** Search results read at most about this many characters of a description. */
const DESCRIPTION_MAX = 165;

/** The glimpse, cut at a word when a result would cut it anyway. Never scripture. */
export function describe(glimpse: string): string {
  // By code points, so an emoji is never split into a lone surrogate.
  const points = Array.from(glimpse);
  if (points.length <= DESCRIPTION_MAX) {
    return glimpse;
  }
  const room = points.slice(0, DESCRIPTION_MAX - 1).join('');
  const cut = room.lastIndexOf(' ');
  return `${(cut > 0 ? room.slice(0, cut) : room).trimEnd()}…`;
}

/** What the page tells search engines: its title and glimpse, never the verse or the hadith. */
export function publicInsightSeo(insight: PublicInsight): PageSeo {
  return {
    path: publicInsightPath(insight.id),
    title: insight.title,
    description: describe(insight.glimpse),
    type: 'article',
  };
}

export function publicInsightMetadata(insight: PublicInsight) {
  return pageMetadata(publicInsightSeo(insight));
}
