// @vitest-environment node
import sharp from 'sharp';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { ENTRY } from '@/test/atlas';
import { GET } from './route';

function get(id: string) {
  return GET(new Request(`https://tabsira.test/atlas/entries/${id}/preview`), {
    params: Promise.resolve({ id }),
  });
}

describe('GET /atlas/entries/{id}/preview', () => {
  it('answers the 1200 x 630 preview of a published entry', async () => {
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY } });
    const response = await get(ENTRY.id);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/jpeg');
    const meta = await sharp(Buffer.from(await response.arrayBuffer())).metadata();
    expect([meta.width, meta.height]).toEqual([1200, 630]);
  });

  it('answers 404 for what is not public or not an id, 503 when the API does not answer', async () => {
    expect((await get('0')).status).toBe(404);
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: apiError(404, 'NOT_FOUND') });
    expect((await get(ENTRY.id)).status).toBe(404);
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: 'network-error' });
    expect((await get(ENTRY.id)).status).toBe(503);
  });
});
