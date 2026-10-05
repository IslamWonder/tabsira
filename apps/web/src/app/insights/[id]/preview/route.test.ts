// @vitest-environment node
import sharp from 'sharp';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Busy } from '@/lib/share-card/limiter';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/share';
import { GET } from './route';

const ID = '110000000000000002';

function get(id: string) {
  return GET(new Request(`https://tabsira.test/insights/${id}/preview`), {
    params: Promise.resolve({ id }),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('GET /insights/{id}/preview', () => {
  it('answers a 1200 x 630 JPEG that no cache keeps', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await get(ID);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/jpeg');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    const bytes = Buffer.from(await response.arrayBuffer());
    const meta = await sharp(bytes).metadata();
    expect([meta.format, meta.width, meta.height]).toEqual(['jpeg', 1200, 630]);
    // Under 300 KB, or messaging apps show no preview.
    expect(bytes.length).toBeLessThan(300_000);
    expect(response.headers.get('Content-Length')).toBe(String(bytes.length));
  });

  it('answers 404 for what is not public and 503 when the API does not answer', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    expect((await get(ID)).status).toBe(404);
    expect((await get('abc')).status).toBe(404);
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    expect((await get(ID)).status).toBe(503);
  });

  it('tells a client to retry when this process is busy, and lets other errors through', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const preview = await import('@/lib/share-card/preview');
    const spy = vi.spyOn(preview, 'previewJpeg').mockRejectedValueOnce(new Busy());
    const busy = await get(ID);
    expect(busy.status).toBe(503);
    expect(busy.headers.get('Retry-After')).toBe('2');
    spy.mockRejectedValueOnce(new Error('boom'));
    await expect(get(ID)).rejects.toThrow('boom');
  });
});
