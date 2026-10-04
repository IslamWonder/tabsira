import { afterEach, describe, expect, it, vi } from 'vitest';
import { SERVER_API_TIMEOUT_MS } from '@/config/server-env';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/share';
import { loadPublicInsight } from './load';

const ID = '110000000000000002';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('reading a published insight for its card', () => {
  it('returns the insight the API answers', async () => {
    const insight = publicInsightOut();
    mockApi({ [`GET /public/insights/${ID}`]: { body: insight } });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'insight', insight });
  });

  it("asks the server's own API address, with a timeout, no cookie, no redirect and no cache", async () => {
    vi.stubEnv('API_INTERNAL_URL', 'http://127.0.0.1:8123');
    const timeout = vi.spyOn(AbortSignal, 'timeout');
    const api = mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    await loadPublicInsight(ID);
    const request = api.requests[0] as Request;
    expect(new URL(request.url).origin).toBe('http://127.0.0.1:8123');
    expect(timeout).toHaveBeenCalledWith(SERVER_API_TIMEOUT_MS);
    expect(request.headers.get('cookie')).toBeNull();
    // A redirect is refused and nothing is cached: both are options of the fetch itself.
    expect(vi.mocked(globalThis.fetch).mock.calls[0]?.[1]).toMatchObject({
      redirect: 'error',
      cache: 'no-store',
    });
  });

  it('answers the same not-found for 400, 404 and 422, and for a malformed id without asking', async () => {
    for (const status of [400, 404, 422]) {
      const api = mockApi({ [`GET /public/insights/${ID}`]: apiError(status, 'NOT_FOUND') });
      expect(await loadPublicInsight(ID)).toEqual({ kind: 'not-found' });
      expect(api.requests).toHaveLength(1);
    }
    const api = mockApi({});
    expect(await loadPublicInsight('not-an-id')).toEqual({ kind: 'not-found' });
    expect(api.requests).toHaveLength(0);
  });

  it('says unavailable, not gone, for any other answer, a refused redirect or no answer', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(503, 'SERVICE_UNAVAILABLE') });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'unavailable' });
    mockApi({ [`GET /public/insights/${ID}`]: apiError(302, 'HTTP_ERROR') });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'unavailable' });
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'unavailable' });
  });
});
