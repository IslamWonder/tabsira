// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CARD_MAX_BYTES } from '@/lib/share-card/compose';
import { Busy } from '@/lib/share-card/limiter';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/share';
import { GET, HEAD } from './route';

const ID = '110000000000000002';

function get(id: string) {
  return GET(new Request(`https://tabsira.test/insights/${id}/card`), {
    params: Promise.resolve({ id }),
  });
}

describe('GET /insights/{id}/card', () => {
  it('answers a PNG that no cache keeps, so a withdrawal shows at once', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await get(ID);
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/png');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    const bytes = Buffer.from(await response.arrayBuffer());
    expect(bytes.subarray(1, 4).toString()).toBe('PNG');
    // Under 300 KB, or messaging apps show no preview (v2 §25).
    expect(bytes.length).toBeLessThan(CARD_MAX_BYTES);
    expect(response.headers.get('Content-Length')).toBe(String(bytes.length));
  });

  it('answers 404 for anything that is not public, with nothing cached', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    for (const id of [ID, 'abc']) {
      const response = await get(id);
      expect(response.status).toBe(404);
      expect(response.headers.get('Cache-Control')).toBe('no-store');
      expect(await response.text()).toBe('');
    }
  });

  it('answers 503 when the API does not answer, so a crawler tries again', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    const response = await get(ID);
    expect(response.status).toBe(503);
    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });
});

describe('HEAD /insights/{id}/card', () => {
  it('says what GET would say without drawing a card', async () => {
    const draw = vi.spyOn(await import('@/lib/share-card/service'), 'cardPng');
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await HEAD(new Request('https://tabsira.test/x', { method: 'HEAD' }), {
      params: Promise.resolve({ id: ID }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('image/png');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
    expect(await response.text()).toBe('');
    expect(draw).not.toHaveBeenCalled();
  });

  it('answers 404 for what is not public and 503 when the API does not answer', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    const head = (id: string) =>
      HEAD(new Request('https://tabsira.test/x', { method: 'HEAD' }), {
        params: Promise.resolve({ id }),
      });
    expect((await head(ID)).status).toBe(404);
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    expect((await head(ID)).status).toBe(503);
  });
});

describe('GET /insights/{id}/card under load', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('tells a client to retry when this process is drawing as many cards as it takes on', async () => {
    const service = await import('@/lib/share-card/service');
    vi.spyOn(service, 'cardPng').mockRejectedValue(new Busy());
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const response = await get(ID);
    expect(response.status).toBe(503);
    expect(response.headers.get('Retry-After')).toBe('2');
    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });

  it('does not hide a fault of its own as a busy answer', async () => {
    const service = await import('@/lib/share-card/service');
    vi.spyOn(service, 'cardPng').mockRejectedValue(new Error('broken'));
    mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    await expect(get(ID)).rejects.toThrow('broken');
  });

  it('answers the same card from memory the second time, asking the API each time', async () => {
    const api = mockApi({ [`GET /public/insights/${ID}`]: { body: publicInsightOut() } });
    const first = Buffer.from(await (await get(ID)).arrayBuffer());
    const second = Buffer.from(await (await get(ID)).arrayBuffer());
    expect(second.equals(first)).toBe(true);
    expect(api.requests).toHaveLength(2);
  });
});
