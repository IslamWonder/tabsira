import { serverSiteOrigin } from '@/config/server-env';
import type { Result } from '@/lib/api/result';
import { Busy } from './limiter';
import { type PreviewSubject, previewJpeg } from './preview';

/*
 * The answer of a link preview route (og:image) of a public page: an insight,
 * a post or a map entry. Never cached by a browser or a proxy, so a withdrawal
 * shows at once. What a stranger may not read is a 404, an API that did not
 * answer properly a 503, so a crawler tries again rather than forgets the page.
 */
const NO_STORE = 'no-store';
const RETRY_AFTER = '2';

/** The answers of the API that a public page also reads as «not found». */
const NOT_SHOWN: ReadonlySet<number> = new Set([400, 403, 404, 422]);

export type PreviewLoad =
  | { kind: 'subject'; subject: PreviewSubject }
  | { kind: 'not-found' }
  | { kind: 'unavailable' };

export const NOT_FOUND: PreviewLoad = { kind: 'not-found' };

/** What the API answered, as a preview: `pick` returns null for what is not public. */
export function previewLoad<T>(
  result: Result<T>,
  pick: (data: T) => PreviewSubject | null
): PreviewLoad {
  if (!result.ok) {
    return NOT_SHOWN.has(result.status) ? NOT_FOUND : { kind: 'unavailable' };
  }
  const subject = pick(result.data);
  return subject === null ? NOT_FOUND : { kind: 'subject', subject };
}

function plain(status: number, headers: Record<string, string> = {}): Response {
  return new Response(null, { status, headers: { 'Cache-Control': NO_STORE, ...headers } });
}

export async function previewResponse(loaded: PreviewLoad): Promise<Response> {
  if (loaded.kind === 'not-found') {
    return plain(404);
  }
  if (loaded.kind === 'unavailable') {
    return plain(503);
  }
  try {
    const bytes = await previewJpeg(loaded.subject, serverSiteOrigin().host);
    return new Response(new Uint8Array(bytes), {
      headers: {
        'Content-Type': 'image/jpeg',
        'Cache-Control': NO_STORE,
        'Content-Length': String(bytes.length),
      },
    });
  } catch (error) {
    if (error instanceof Busy) {
      return plain(503, { 'Retry-After': RETRY_AFTER });
    }
    throw error;
  }
}
