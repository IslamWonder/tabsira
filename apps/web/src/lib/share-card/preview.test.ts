// @vitest-environment node
import sharp from 'sharp';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { publicInsightOut } from '@/test/share';
import { fetchPhoto, PHOTO_MAX_BYTES, previewJpeg, renderPreview } from './preview';

const PHOTO_URL = 'https://media.tabsira.me/public/aaaa.jpg';

async function photo(width = 1600, height = 900): Promise<Buffer> {
  return sharp({ create: { width, height, channels: 3, background: '#3a7bd5' } })
    .jpeg()
    .toBuffer();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchPhoto', () => {
  it('reads the published photo, and nothing that is not an address or answers badly', async () => {
    const bytes = await photo();
    const fetch = vi.fn().mockImplementation(async () => new Response(new Uint8Array(bytes)));
    vi.stubGlobal('fetch', fetch);
    expect(await fetchPhoto(PHOTO_URL)).toEqual(bytes);
    expect(fetch.mock.calls[0]?.[1]).toMatchObject({ redirect: 'error', cache: 'no-store' });
    expect(await fetchPhoto(null)).toBeNull();
    expect(await fetchPhoto('ftp://x/y.jpg')).toBeNull();
    expect(await fetchPhoto('http://media.tabsira.test/public/a.jpg')).toEqual(bytes);

    fetch.mockResolvedValueOnce(new Response(null, { status: 404 }));
    expect(await fetchPhoto(PHOTO_URL)).toBeNull();
    fetch.mockResolvedValueOnce(
      new Response('x', { headers: { 'content-length': String(PHOTO_MAX_BYTES + 1) } })
    );
    expect(await fetchPhoto(PHOTO_URL)).toBeNull();
    fetch.mockResolvedValueOnce(new Response(new Uint8Array(PHOTO_MAX_BYTES + 1)));
    expect(await fetchPhoto(PHOTO_URL)).toBeNull();
    fetch.mockRejectedValueOnce(new TypeError('offline'));
    expect(await fetchPhoto(PHOTO_URL)).toBeNull();
  });
});

describe('renderPreview', () => {
  it('fills the preview with the photo, darkened under the text', async () => {
    const insight = publicInsightOut({ photo_url: PHOTO_URL });
    const withPhoto = await renderPreview(insight, 'tabsira.me', await photo());
    const without = await renderPreview(insight, 'tabsira.me', null);
    for (const image of [withPhoto, without]) {
      const meta = await sharp(image).metadata();
      expect([meta.width, meta.height]).toEqual([1200, 630]);
    }
    // The photo shows through at the top: the two pictures differ there.
    const top = (image: Buffer) =>
      sharp(image).extract({ left: 400, top: 120, width: 200, height: 60 }).stats();
    expect((await top(withPhoto)).channels[2]?.mean).toBeGreaterThan(
      (await top(without)).channels[2]?.mean ?? 0
    );
  });

  it('falls back to the night ground for a file that is not an image, and drops a long glimpse', async () => {
    const insight = publicInsightOut({ glimpse: 'لمحة طويلة جدًا '.repeat(40) });
    const image = await renderPreview(insight, 'tabsira.me', Buffer.from('not an image'));
    expect((await sharp(image).metadata()).width).toBe(1200);
  });
});

describe('previewJpeg', () => {
  it('draws once for the same content and fetches the photo only then', async () => {
    const bytes = await photo();
    const fetch = vi.fn().mockResolvedValue(new Response(new Uint8Array(bytes)));
    vi.stubGlobal('fetch', fetch);
    const insight = publicInsightOut({ photo_url: PHOTO_URL, title: 'عنوان للذاكرة' });
    const first = await previewJpeg(insight, 'tabsira.me');
    const second = await previewJpeg(insight, 'tabsira.me');
    expect(second).toBe(first);
    expect(fetch).toHaveBeenCalledOnce();
  });
});
