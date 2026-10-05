import { serverSiteOrigin } from '@/config/server-env';
import { Busy } from '@/lib/share-card/limiter';
import { loadPublicInsight } from '@/lib/share-card/load';
import { previewJpeg } from '@/lib/share-card/preview';

/*
 * The link preview image of a published insight (og:image): 1200 x 630 with
 * the published photo, if any, the title and the glimpse. Like the share card,
 * never cached by a browser or a proxy, so a withdrawal shows at once.
 */
const NO_STORE = 'no-store';
const RETRY_AFTER = '2';

type Context = { params: Promise<{ id: string }> };

function plain(status: number, headers: Record<string, string> = {}): Response {
  return new Response(null, { status, headers: { 'Cache-Control': NO_STORE, ...headers } });
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
    const bytes = await previewJpeg(loaded.insight, serverSiteOrigin().host);
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
