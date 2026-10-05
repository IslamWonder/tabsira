import { SERVER_API_TIMEOUT_MS, serverApiOrigin } from '@/config/server-env';
import { createApiClient } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type CommunitySummary = components['schemas']['CommunitySummary'];

/** The API keeps its answer ten minutes; the page asks again no sooner. */
export const COMMUNITY_REVALIDATE_SECONDS = 600;

/** Below this many members the box stays hidden: a young community is not shown as small numbers. */
export const COMMUNITY_MIN_MEMBERS = 50;

/**
 * The public counts as a stranger sees them, read by the web server with no cookie. A short
 * timeout: a slow or absent API leaves the box out and never holds the home page.
 */
export function communitySummaryOnServer(): Promise<Result<CommunitySummary>> {
  const client = createApiClient({
    baseUrl: serverApiOrigin(),
    fetch: (request) =>
      globalThis.fetch(request, { next: { revalidate: COMMUNITY_REVALIDATE_SECONDS } }),
  });
  return attempt(
    client.GET('/community/summary', { signal: AbortSignal.timeout(SERVER_API_TIMEOUT_MS) })
  );
}

/** The summary worth showing, or null: the API failed, or the community is still small. */
export function shownSummary(result: Result<CommunitySummary>): CommunitySummary | null {
  return result.ok && result.data.members >= COMMUNITY_MIN_MEMBERS ? result.data : null;
}
