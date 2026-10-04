import { describe, expect, it } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { publicInsightOut } from '@/test/share';
import { loadPublicInsight } from './load';

const ID = '110000000000000002';

describe('reading a published insight for its card', () => {
  it('returns the insight the API answers', async () => {
    const insight = publicInsightOut();
    const api = mockApi({ [`GET /public/insights/${ID}`]: { body: insight } });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'insight', insight });
    // Nothing of the visitor goes with it, and no cached answer is reused.
    expect(api.requests[0]?.cache).toBe('no-store');
  });

  it('answers the same not-found for anything the API does not show, and for a malformed id', async () => {
    const api = mockApi({ [`GET /public/insights/${ID}`]: apiError(404, 'NOT_FOUND') });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'not-found' });
    expect(await loadPublicInsight('not-an-id')).toEqual({ kind: 'not-found' });
    expect(api.requests).toHaveLength(1);
  });

  it('says unavailable, not gone, when the API did not answer or failed', async () => {
    mockApi({ [`GET /public/insights/${ID}`]: apiError(503, 'SERVICE_UNAVAILABLE') });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'unavailable' });
    mockApi({ [`GET /public/insights/${ID}`]: 'network-error' });
    expect(await loadPublicInsight(ID)).toEqual({ kind: 'unavailable' });
  });
});
