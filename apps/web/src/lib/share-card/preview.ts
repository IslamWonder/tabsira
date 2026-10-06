import { readFile } from 'node:fs/promises';
import path from 'node:path';
import sharp, { type OverlayOptions } from 'sharp';
import { messages } from '@/messages';
import { cardKey, createPngCache } from './cache';
import { COLOUR } from './compose';
import { cardFaces } from './fonts';
import { createLimiter } from './limiter';
import { PREVIEW_HEIGHT, PREVIEW_WIDTH } from './preview-size';
import { drawText } from './text-image';

/*
 * The link preview of a published insight (WhatsApp, Facebook, X, Telegram...):
 * 1200 x 630, the size they all crop to. The photo fills it when its owner
 * already published it (a public post or map entry made its public copy, which
 * the API gives as `photo_url`); otherwise the night ground of the brand. Over
 * it, darkened at the bottom so it reads on any photo: the title, the glimpse,
 * the mark and the site's name. Never the verse or the hadith: a preview is cut
 * and resized by others, and scripture is shown whole or not at all.
 */

const MARGIN = 64;
const TEXT_WIDTH = PREVIEW_WIDTH - 2 * MARGIN;
const MARK_SIZE = 84;
/** A photo larger than this is not drawn: the preview falls back to the night ground. */
export const PHOTO_MAX_BYTES = 12 * 1024 * 1024;
const PHOTO_TIMEOUT_MS = 5000;

/** What a preview draws: a published insight, a public post's insight or a map entry. */
export interface PreviewSubject {
  title: string;
  glimpse: string;
  /** The public copy of the photo, when its owner already published it. */
  photo_url?: string | null;
}

const limiter = createLimiter(2, 4);
const cache = createPngCache(32);

/** The published photo's bytes, or null when there is none or it cannot be read in time. */
export async function fetchPhoto(url: string | null | undefined): Promise<Buffer | null> {
  if (!url?.startsWith('https://') && !url?.startsWith('http://')) {
    return null;
  }
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(PHOTO_TIMEOUT_MS),
      redirect: 'error',
      cache: 'no-store',
    });
    const length = Number(response.headers.get('content-length') ?? '0');
    if (!response.ok || length > PHOTO_MAX_BYTES) {
      return null;
    }
    const bytes = Buffer.from(await response.arrayBuffer());
    return bytes.length > PHOTO_MAX_BYTES ? null : bytes;
  } catch {
    return null;
  }
}

function nightGround(): Buffer {
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${PREVIEW_WIDTH}" height="${PREVIEW_HEIGHT}">
  <defs><radialGradient id="g" cx="80%" cy="0%" r="80%">
    <stop offset="0" stop-color="#1F9E6E" stop-opacity="0.28"/><stop offset="1" stop-color="#1F9E6E" stop-opacity="0"/>
  </radialGradient></defs>
  <rect width="100%" height="100%" fill="${COLOUR.ground}"/><rect width="100%" height="100%" fill="url(#g)"/>
</svg>`);
}

/** Darker towards the bottom, where the text sits, so it reads on any photo. */
function veil(withPhoto: boolean): Buffer {
  const top = withPhoto ? 0.15 : 0;
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${PREVIEW_WIDTH}" height="${PREVIEW_HEIGHT}">
  <defs><linearGradient id="v" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="${COLOUR.ground}" stop-opacity="${top}"/>
    <stop offset="0.45" stop-color="${COLOUR.ground}" stop-opacity="${withPhoto ? 0.35 : 0}"/>
    <stop offset="1" stop-color="${COLOUR.ground}" stop-opacity="${withPhoto ? 0.9 : 0}"/>
  </linearGradient></defs>
  <rect width="100%" height="100%" fill="url(#v)"/>
</svg>`);
}

async function ground(photo: Buffer | null): Promise<{ image: Buffer; photo: boolean }> {
  if (photo !== null) {
    try {
      const image = await sharp(photo)
        .rotate()
        .resize(PREVIEW_WIDTH, PREVIEW_HEIGHT, { fit: 'cover', position: 'attention' })
        .png()
        .toBuffer();
      return { image, photo: true };
    } catch {
      // Not an image sharp can read: the night ground instead.
    }
  }
  return { image: await sharp(nightGround()).png().toBuffer(), photo: false };
}

/** The preview, drawn from the insight as the API returned it and the published photo, if any. */
export async function renderPreview(
  insight: PreviewSubject,
  host: string,
  photo: Buffer | null
): Promise<Buffer> {
  const faces = cardFaces();
  const face = faces.text[0] as (typeof faces.text)[number];
  const latin = faces.text[2] as (typeof faces.text)[number];
  const base = await ground(photo);
  const [title, glimpse, name, site, mark] = await Promise.all([
    drawText({
      text: insight.title,
      face,
      weight: 600,
      size: 60,
      leading: 0.2,
      width: TEXT_WIDTH,
      align: 'start',
      colour: COLOUR.text,
    }),
    drawText({
      text: insight.glimpse,
      face,
      size: 32,
      leading: 0.3,
      width: TEXT_WIDTH,
      align: 'start',
      colour: COLOUR.soft,
    }),
    drawText({
      text: messages.brand.name,
      face,
      weight: 600,
      size: 34,
      leading: 0,
      width: 400,
      align: 'start',
      colour: COLOUR.gold,
    }),
    drawText({
      text: host,
      face: latin,
      size: 24,
      leading: 0,
      width: 600,
      align: 'start',
      colour: COLOUR.muted,
    }),
    readFile(
      path.join(/* turbopackIgnore: true */ process.cwd(), 'public/icons/icon-192.png')
    ).then((icon) => sharp(icon).resize(MARK_SIZE, MARK_SIZE).png().toBuffer()),
  ]);
  // From the bottom up: the site's name, the glimpse (when it fits), the title.
  const siteTop = PREVIEW_HEIGHT - MARGIN + 8 - site.height;
  const glimpseFits = glimpse.height <= 3 * 32 * 1.4;
  const glimpseTop = siteTop - 24 - (glimpseFits ? glimpse.height : 0);
  const titleTop = Math.max(MARGIN + MARK_SIZE + 16, glimpseTop - 16 - title.height);
  const right = (width: number) => Math.round(PREVIEW_WIDTH - MARGIN - width);
  const layers: OverlayOptions[] = [
    { input: veil(base.photo), left: 0, top: 0 },
    { input: mark, left: PREVIEW_WIDTH - MARGIN - MARK_SIZE, top: MARGIN - 16 },
    {
      input: name.png,
      left: right(MARK_SIZE + 16 + name.width),
      top: Math.round(MARGIN - 16 + (MARK_SIZE - name.height) / 2),
    },
    { input: title.png, left: right(title.width), top: Math.round(titleTop) },
    { input: site.png, left: MARGIN, top: Math.round(siteTop) },
  ];
  if (glimpseFits) {
    layers.push({ input: glimpse.png, left: right(glimpse.width), top: Math.round(glimpseTop) });
  }
  return sharp(base.image).composite(layers).jpeg({ quality: 82, mozjpeg: true }).toBuffer();
}

/** The preview of an insight: from memory when this very content was just drawn. */
export async function previewJpeg(insight: PreviewSubject, host: string): Promise<Buffer> {
  // Only what is drawn makes the key, so the same post and insight share one image.
  const key = `preview:${cardKey([insight.title, insight.glimpse, insight.photo_url ?? null], host)}`;
  const known = cache.get(key);
  if (known !== undefined) {
    return known;
  }
  const photo = await fetchPhoto(insight.photo_url);
  const jpeg = await limiter.run(() => renderPreview(insight, host, photo));
  cache.set(key, jpeg);
  return jpeg;
}
