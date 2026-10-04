import { ImageResponse } from 'next/og';
import { CARD_HEIGHT, CARD_WIDTH, shareCard } from '@/components/insight/share-card';
import { serverSiteOrigin } from '@/config/server-env';
import { loadPublicInsight } from '@/lib/public-insight';
import { isPublicId } from '@/lib/scan/ids';
import { cardFonts, coveredCodePoints } from '@/lib/share-card-fonts';

/*
 * The share card of a published insight as a PNG (master prompt v2 §18), drawn on
 * the server from the same public payload as the page, so it can never show more
 * than the page does. Private, withdrawn and missing insights answer 404 alike.
 * Drawing costs a few hundred milliseconds of CPU, so a drawn card is kept for
 * five minutes per process (the same time caches may keep it), keyed by the
 * insight and its publication time: a withdrawn and republished insight is drawn
 * again.
 */

export const dynamic = 'force-dynamic';

export const CACHE_SECONDS = 300;
const CACHE_MAX = 100;
// Unknown, unpublished, withdrawn and malformed are one answer, as on the page.
const NOT_SHOWN: ReadonlySet<number> = new Set([400, 404, 422]);
const drawn = new Map<string, { at: number; png: ArrayBuffer }>();

function remembered(key: string, now: number): ArrayBuffer | undefined {
  const entry = drawn.get(key);
  if (entry === undefined) {
    return undefined;
  }
  if (now - entry.at > CACHE_SECONDS * 1000) {
    drawn.delete(key);
    return undefined;
  }
  return entry.png;
}

function remember(key: string, png: ArrayBuffer, now: number): void {
  if (drawn.size >= CACHE_MAX) {
    // A full map always has a first key.
    drawn.delete(drawn.keys().next().value as string);
  }
  drawn.set(key, { at: now, png });
}

/** For tests: forget every drawn card. */
export function forgetDrawnCards(): void {
  drawn.clear();
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isPublicId(id)) {
    return new Response(null, { status: 404 });
  }
  const result = await loadPublicInsight(id);
  if (!result.ok) {
    if (NOT_SHOWN.has(result.status)) {
      return new Response(null, { status: 404 });
    }
    throw new Error(`share card unavailable: ${result.code}`);
  }
  const insight = result.data;
  const key = `${insight.id}@${insight.published_at}`;
  const now = Date.now();
  let png = remembered(key, now);
  if (png === undefined) {
    const [fonts, covered] = await Promise.all([cardFonts(), coveredCodePoints()]);
    // Drawn whole before anything is sent: a failure is a 500, never a broken image behind a 200.
    png = await new ImageResponse(shareCard(insight, serverSiteOrigin(), covered), {
      width: CARD_WIDTH,
      height: CARD_HEIGHT,
      fonts,
    }).arrayBuffer();
    remember(key, png, now);
  }
  return new Response(png, {
    status: 200,
    headers: {
      'Content-Type': 'image/png',
      'Content-Length': String(png.byteLength),
      'Cache-Control': `public, max-age=${CACHE_SECONDS}`,
    },
  });
}
