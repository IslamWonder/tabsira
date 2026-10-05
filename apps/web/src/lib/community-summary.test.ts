import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import {
  COMMUNITY_MIN_MEMBERS,
  COMMUNITY_REVALIDATE_SECONDS,
  type CommunitySummary,
  communitySummaryOnServer,
  shownSummary,
} from './community-summary';

const SUMMARY: CommunitySummary = {
  members: 120,
  insights: 300,
  reactions: 900,
  atlas_entries: 80,
  countries: 12,
  sponsorships_open: 4,
};

describe('communitySummaryOnServer', () => {
  it('reads the public counts with no cookie, kept ten minutes by the web server', async () => {
    const api = mockApi({ 'GET /community/summary': { body: SUMMARY } });

    const result = await communitySummaryOnServer();

    expect(result).toEqual({ ok: true, data: SUMMARY, status: 200 });
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
    const init = vi.mocked(globalThis.fetch).mock.calls[0]?.[1];
    expect(init).toEqual({ next: { revalidate: COMMUNITY_REVALIDATE_SECONDS } });
  });

  it('turns a database that is down into a failure the page can skip', async () => {
    mockApi({ 'GET /community/summary': apiError(503, 'SERVICE_UNAVAILABLE') });

    const result = await communitySummaryOnServer();

    expect(result.ok).toBe(false);
    expect(shownSummary(result)).toBeNull();
  });
});

describe('shownSummary', () => {
  it('shows a community of at least the threshold', () => {
    const at = { ...SUMMARY, members: COMMUNITY_MIN_MEMBERS };
    expect(shownSummary({ ok: true, data: at, status: 200 })).toBe(at);
  });

  it('hides a community still under the threshold', () => {
    const small = { ...SUMMARY, members: COMMUNITY_MIN_MEMBERS - 1 };
    expect(shownSummary({ ok: true, data: small, status: 200 })).toBeNull();
  });

  it('hides the box when the API never answered', () => {
    expect(
      shownSummary({ ok: false, code: 'NETWORK', status: 0, fields: [], retryAfter: null })
    ).toBeNull();
  });
});
