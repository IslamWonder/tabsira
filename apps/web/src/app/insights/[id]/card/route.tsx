import { serverSiteOrigin } from '@/config/server-env';
import { Busy } from '@/lib/share-card/limiter';
import { loadPublicInsight } from '@/lib/share-card/load';
import { cardPng } from '@/lib/share-card/service';

/*
 * The share card of a published insight (task 09.3): a PNG with the verse and
 * the hadith as the API returns them. Never cached by a browser or a proxy: the
 * public API answers `no-store` so a withdrawal shows at once, and an image
 * kept by a cache would go on showing a withdrawn insight. The API is asked at
 * every request; only the drawing is remembered in this process (service.ts).
 */
const NO_STORE = 'no-store';
/** Seconds a client should wait when this process is drawing as many cards as it takes on. */
const RETRY_AFTER = '2';

type Context = { params: Promise<{ id: string }> };

function plain(status: number, headers: Record<string, string> = {}): Response {
  return new Response(null, { status, headers: { 'Cache-Control': NO_STORE, ...headers } });
}

function png(bytes: Buffer): Response {
  return new Response(new Uint8Array(bytes), {
    headers: {
      'Content-Type': 'image/png',
      'Cache-Control': NO_STORE,
      'Content-Length': String(bytes.length),
    },
  });
}

export async function GET(_request: Request, { params }: Context) {
  const { id } = await params;
  const loaded = await loadPublicInsight(id);
  if (loaded.kind === 'not-found') {
    return plain(404);
  }
  if (loaded.kind === 'unavailable') {
    return plain(503);
  }
  try {
    const bytes = await cardPng(loaded.insight, serverSiteOrigin().host);
    return png(bytes);
  } catch (error) {
    if (error instanceof Busy) {
      return plain(503, { 'Retry-After': RETRY_AFTER });
    }
    throw error;
  }
}

/** Says what GET would say without drawing anything: the status and the type, no body. */
export async function HEAD(_request: Request, { params }: Context) {
  const { id } = await params;
  const loaded = await loadPublicInsight(id);
  if (loaded.kind === 'not-found') {
    return plain(404);
  }
  if (loaded.kind === 'unavailable') {
    return plain(503);
  }
  return new Response(null, {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': NO_STORE },
  });
}
