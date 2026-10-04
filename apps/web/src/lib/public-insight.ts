import { cache } from 'react';
import { serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt } from '@/lib/api/result';
import type { PublicInsight } from '@/lib/scan/api';
import type { PageSeo } from '@/lib/seo';
import { messages } from '@/messages';

/*
 * The public page of a published insight (master prompt v2 §18), read by the web
 * server from the API's public route. The API decides what is public: a private,
 * withdrawn or missing insight is a 404 there and a not-found page here. The page
 * never adds anything of the owner beyond what the API returns.
 */

/** A reader or a crawler waits this long for the API; the consent check's budget is too short here. */
export const PUBLIC_INSIGHT_TIMEOUT_MS = 4000;

/** The length limits of docs/SEO.md §2, with room for the title template. */
export const TITLE_MAX = 56;
export const DESCRIPTION_MAX = 165;

export function publicInsightPath(id: string): string {
  return `/i/${id}`;
}

/** The share card drawn for the insight (`/i/{id}/card.png`, 1200×630). */
export function publicInsightCardPath(id: string): string {
  return `${publicInsightPath(id)}/card.png`;
}

/** Cut a platform text at a word boundary so it fits `max` characters, with an ellipsis. */
export function clip(text: string, max: number): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) {
    return trimmed;
  }
  const room = trimmed.slice(0, max - 1);
  const atWord = room.lastIndexOf(' ');
  return `${(atWord > max / 2 ? room.slice(0, atWord) : room).trimEnd()}…`;
}

/** Fetch a published insight once per request; `null` when the API says there is none. */
export const fetchPublicInsight = cache(async (id: string): Promise<PublicInsight | null> => {
  const client = createApiClient({ baseUrl: serverApiOrigin() });
  const result = await attempt(
    client.GET('/public/insights/{insight_id}', {
      params: { path: { insight_id: id } },
      signal: AbortSignal.timeout(PUBLIC_INSIGHT_TIMEOUT_MS),
    })
  );
  if (result.ok) {
    return result.data;
  }
  // Nothing public there, or an id the API refuses (19 digits beyond its range): the same page.
  if (result.status === 404 || result.status === 422) {
    return null;
  }
  throw new Error(`public insight ${id}: ${result.code} (${result.status})`);
});

/** The search metadata of a public insight: its own title and glimpse, nothing of its owner. */
export function publicInsightSeo(insight: PublicInsight): PageSeo {
  const T = messages.publicInsight;
  return {
    path: publicInsightPath(insight.id),
    title: clip(insight.title, TITLE_MAX),
    description: clip(`${T.descriptionPrefix} ${insight.glimpse}`, DESCRIPTION_MAX),
    type: 'article',
    image: {
      url: publicInsightCardPath(insight.id),
      width: 1200,
      height: 630,
      alt: clip(insight.title, TITLE_MAX),
    },
  };
}
