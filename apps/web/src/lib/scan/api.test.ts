import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import {
  chatReply,
  completionOut,
  insightOut,
  progressOut,
  scanOut,
  tutorialOut,
} from '@/test/scan';
import {
  apiUrl,
  askInsight,
  clarifyScan,
  completeInsight,
  declareAction,
  focusScan,
  getInsight,
  getProgress,
  getRainTutorial,
  getScan,
  keepRainInsight,
  openScanStream,
  rateInsight,
  startScanFromFile,
  startScanFromLink,
} from './api';

const ID = '110000000000000001';

describe('the calls of the journey', () => {
  it('starts a scan from a photo, as a multipart upload', async () => {
    const api = mockApi({ 'POST /scans': { status: 202, body: scanOut({ status: 'queued' }) } });
    const result = await startScanFromFile(new File(['x'], 'a.jpg', { type: 'image/jpeg' }));
    expect(result).toMatchObject({ ok: true, status: 202 });
    expect(api.requests[0]?.method).toBe('POST');
    expect(api.requests[0]?.headers.get('content-type') ?? '').not.toContain('application/json');
  });

  it('starts a scan from a link, as JSON', async () => {
    const api = mockApi({ 'POST /scans': { status: 202, body: scanOut({ status: 'queued' }) } });
    await startScanFromLink('https://example.org/a.jpg');
    expect(await api.bodies('POST', '/scans')).toEqual([{ url: 'https://example.org/a.jpg' }]);
  });

  it('keeps a public id a string all the way into the path', async () => {
    const api = mockApi({ [`GET /scans/${ID}`]: { body: scanOut() } });
    const result = await getScan(ID);
    expect(result.ok).toBe(true);
    expect(new URL(api.requests[0]?.url as string).pathname).toBe(`/scans/${ID}`);
  });

  it('points at a thing, and answers the question', async () => {
    const api = mockApi({
      [`POST /scans/${ID}/focus`]: { status: 202, body: scanOut({ run: 2 }) },
      [`POST /scans/${ID}/clarify`]: { status: 202, body: scanOut({ run: 3 }) },
    });
    await focusScan(ID, 'e1');
    await clarifyScan(ID, 'جواب');
    expect(await api.bodies('POST', `/scans/${ID}/focus`)).toEqual([{ entity_id: 'e1' }]);
    expect(await api.bodies('POST', `/scans/${ID}/clarify`)).toEqual([{ answer: 'جواب' }]);
  });

  it('reads the tutorial and keeps a copy of one of its insights', async () => {
    mockApi({
      'GET /tutorial/rain': { body: tutorialOut() },
      'POST /tutorial/rain/insights/drop': { body: insightOut() },
    });
    expect((await getRainTutorial()).ok).toBe(true);
    expect((await keepRainInsight('drop')).ok).toBe(true);
  });

  it('reads an insight, asks, declares the step, completes it', async () => {
    const api = mockApi({
      [`GET /insights/${ID}`]: { body: insightOut() },
      [`POST /insights/${ID}/chat`]: { body: chatReply() },
      [`POST /insights/${ID}/action`]: { body: { state: 'done', at: null, means: 'م' } },
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      [`PUT /insights/${ID}/feedback`]: {
        body: {
          helpful: false,
          reasons: ['other'],
          note: null,
          updated_at: '2026-10-05T10:00:00Z',
        },
      },
      'GET /me/progress': { body: progressOut() },
    });
    expect((await getInsight(ID)).ok).toBe(true);
    expect((await askInsight(ID, 'سؤال', 'key-12345678')).ok).toBe(true);
    expect((await declareAction(ID, 'later')).ok).toBe(true);
    expect((await completeInsight(ID)).ok).toBe(true);
    expect((await rateInsight(ID, { helpful: false, reasons: ['other'], note: null })).ok).toBe(
      true
    );
    expect((await getProgress('Africa/Tunis')).ok).toBe(true);
    expect(await api.bodies('POST', `/insights/${ID}/chat`)).toEqual([
      { message: 'سؤال', idempotencyKey: 'key-12345678' },
    ]);
    expect(await api.bodies('POST', `/insights/${ID}/action`)).toEqual([{ choice: 'later' }]);
    expect(await api.bodies('PUT', `/insights/${ID}/feedback`)).toEqual([
      { helpful: false, reasons: ['other'], note: null },
    ]);
    const progress = api.requests.find((request) => request.url.includes('/me/progress'));
    expect(new URL(progress?.url as string).searchParams.get('tz')).toBe('Africa/Tunis');
  });

  it('answers a failure with its stable code', async () => {
    mockApi({ [`GET /scans/${ID}`]: apiError(404, 'NOT_FOUND') });
    expect(await getScan(ID)).toMatchObject({ ok: false, code: 'NOT_FOUND' });
  });
});

describe('the stream of a scan', () => {
  it('is opened on the API with the session, and resumes after the last number', async () => {
    const fetch = vi.fn(async () => new Response(null));
    vi.stubGlobal('fetch', fetch);
    const signal = new AbortController().signal;
    await openScanStream(`/scans/${ID}/events`, null, signal);
    await openScanStream(`/scans/${ID}/events`, '41', signal);
    const [url, first] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    const [, second] = fetch.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe(apiUrl(`/scans/${ID}/events`));
    expect(first.credentials).toBe('include');
    expect(first.headers).toEqual({ Accept: 'text/event-stream' });
    expect(second.headers).toEqual({ Accept: 'text/event-stream', 'Last-Event-ID': '41' });
  });
});
