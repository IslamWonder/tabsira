import { createApiClient } from '@/lib/api/client';
import { attempt } from '@/lib/api/result';
import { isPublicId } from '@/lib/scan/ids';
import type { PublicInsight } from './layout';

export type Loaded =
  | { kind: 'insight'; insight: PublicInsight }
  | { kind: 'not-found' }
  | { kind: 'unavailable' };

/**
 * The published insight for the card, read from the API on the server. Anything
 * that is not public (unpublished, withdrawn, unknown, a malformed id) is the
 * same 'not-found'; only an API that did not answer is 'unavailable', so a
 * crawler is told to try again rather than that the page is gone.
 */
export async function loadPublicInsight(id: string): Promise<Loaded> {
  if (!isPublicId(id)) {
    return { kind: 'not-found' };
  }
  const result = await attempt(
    createApiClient().GET('/public/insights/{insight_id}', {
      params: { path: { insight_id: id } },
      cache: 'no-store',
    })
  );
  if (result.ok) {
    return { kind: 'insight', insight: result.data };
  }
  return result.status === 404 ? { kind: 'not-found' } : { kind: 'unavailable' };
}
