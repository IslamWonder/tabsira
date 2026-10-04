import { loadPublicInsight } from '@/lib/share-card/load';
import { renderCard } from '@/lib/share-card/render';
import { siteOrigin } from '@/lib/site';

/*
 * The share card of a published insight (task 09.3): a PNG with the verse and
 * the hadith as the API returns them. Never cached: the public API answers
 * `no-store` so a withdrawal shows at once, and an image kept by a cache would
 * go on showing a withdrawn insight.
 */
const NO_STORE = 'no-store';

function plain(status: number): Response {
  return new Response(null, { status, headers: { 'Cache-Control': NO_STORE } });
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const loaded = await loadPublicInsight(id);
  if (loaded.kind === 'not-found') {
    return plain(404);
  }
  if (loaded.kind === 'unavailable') {
    return plain(503);
  }
  const png = await renderCard(loaded.insight, siteOrigin().host);
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': NO_STORE },
  });
}
