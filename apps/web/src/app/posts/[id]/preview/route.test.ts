// @vitest-environment node
import sharp from 'sharp';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { POST } from '@/test/social';
import { GET } from './route';

function get(id: string) {
  return GET(new Request(`https://tabsira.test/posts/${id}/preview`), {
    params: Promise.resolve({ id }),
  });
}

describe('GET /posts/{id}/preview', () => {
  it('answers the 1200 x 630 preview of a public post, read with no cookie', async () => {
    const api = mockApi({ [`GET /posts/${POST.id}`]: { body: POST } });
    const response = await get(POST.id);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/jpeg');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    const meta = await sharp(Buffer.from(await response.arrayBuffer())).metadata();
    expect([meta.width, meta.height]).toEqual([1200, 630]);
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
  });

  it('has no preview for a post shown to followers only or not published', async () => {
    for (const post of [
      { ...POST, visibility: 'followers' as const },
      { ...POST, status: 'draft' as const },
    ]) {
      mockApi({ [`GET /posts/${POST.id}`]: { body: post } });
      expect((await get(POST.id)).status).toBe(404);
    }
  });

  it('answers 404 for what is not public or not an id, 503 when the API does not answer', async () => {
    expect((await get('abc')).status).toBe(404);
    mockApi({ [`GET /posts/${POST.id}`]: apiError(403, 'FORBIDDEN') });
    expect((await get(POST.id)).status).toBe(404);
    mockApi({ [`GET /posts/${POST.id}`]: 'network-error' });
    expect((await get(POST.id)).status).toBe(503);
  });
});
