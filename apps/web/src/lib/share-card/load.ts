import { loadPublicInsight as readPublicInsight } from '@/lib/public-insight';
import { isPublicId } from '@/lib/scan/ids';
import type { PublicInsight } from './layout';

export type Loaded =
  | { kind: 'insight'; insight: PublicInsight }
  | { kind: 'not-found' }
  | { kind: 'unavailable' };

/** The answers of the API that the page also reads as «not found»: nothing public is there. */
const NOT_SHOWN: ReadonlySet<number> = new Set([400, 404, 422]);

/**
 * The published insight for the card, read as the public page reads it (the
 * server's own API address, a short timeout, no cookie, no redirect, never
 * cached). Anything that is not public (unpublished, withdrawn, unknown, a
 * malformed id) is the same 'not-found'; only an API that did not answer
 * properly is 'unavailable', so a crawler is told to try again rather than
 * that the page is gone.
 */
export async function loadPublicInsight(id: string): Promise<Loaded> {
  if (!isPublicId(id)) {
    return { kind: 'not-found' };
  }
  const result = await readPublicInsight(id);
  if (result.ok) {
    return { kind: 'insight', insight: result.data };
  }
  return NOT_SHOWN.has(result.status) ? { kind: 'not-found' } : { kind: 'unavailable' };
}
