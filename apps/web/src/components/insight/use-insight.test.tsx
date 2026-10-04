import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { apiError, mockApi, type Route } from '@/test/api';
import { chatReply, completionOut, insightOut, progressOut, scanOut } from '@/test/scan';
import { useInsight } from './use-insight';

const ID = '110000000000000002';
const SCAN = '110000000000000001';

function routes(extra: Record<string, Route> = {}, insight = insightOut()) {
  return mockApi({
    [`GET /insights/${ID}`]: { body: insight },
    [`GET /scans/${SCAN}`]: { body: scanOut() },
    ...extra,
  });
}

async function ready() {
  const view = renderHook(() => useInsight(ID));
  await waitFor(() => expect(view.result.current.load.phase).toBe('ready'));
  return view;
}

describe('useInsight: reading', () => {
  it('reads the insight and finds its photo while the scan keeps it', async () => {
    routes();
    const { result } = renderHook(() => useInsight(ID));
    expect(result.current.load.phase).toBe('loading');
    await waitFor(() => expect(result.current.photo).not.toBeNull());
    expect(result.current.load.phase).toBe('ready');
    expect(result.current.photo).toMatchObject({
      kind: 'photo',
      width: 800,
      height: 600,
      unoptimized: true,
    });
    expect(result.current.step).toEqual({ status: 'idle' });
    expect(result.current.finish.status).toBe('idle');
  });

  it('shows the prepared rain photo for a tutorial insight, without asking for a scan', async () => {
    routes({}, insightOut({ origin: 'tutorial', scan_id: null }));
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.photo).not.toBeNull());
    expect(result.current.photo).toMatchObject({
      kind: 'photo',
      src: '/scene/rain-olive.jpg',
      unoptimized: false,
    });
  });

  it('never fetches the photo of a sensitive scene', async () => {
    const api = routes({}, insightOut({ image: { sensitive: true, url: null } }));
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.photo).toEqual({ kind: 'sensitive' }));
    expect(api.requests.some((request) => request.url.includes('/scans/'))).toBe(false);
  });

  it('says there is no photo when there is no scan, no address, or the scan cannot be read', async () => {
    for (const insight of [
      insightOut({ scan_id: null }),
      insightOut({ image: { sensitive: false, url: null } }),
    ]) {
      routes({}, insight);
      const { result, unmount } = renderHook(() => useInsight(ID));
      await waitFor(() => expect(result.current.photo).toEqual({ kind: 'none' }));
      unmount();
    }
    routes({ [`GET /scans/${SCAN}`]: apiError(404, 'NOT_FOUND') });
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.photo).toEqual({ kind: 'none' }));
  });

  it('says the photo is gone once the scan no longer keeps it', async () => {
    const gone = scanOut({ image: { available: false, width: 800, height: 600, url: null } });
    routes({ [`GET /scans/${SCAN}`]: { body: gone } });
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.photo).toEqual({ kind: 'gone' }));
  });

  it('starts from what was already declared and completed', async () => {
    routes(
      {},
      insightOut({
        action: { state: 'later', at: null, means: '[معنى التأجيل]' },
        completed_at: '2026-10-04T08:05:00Z',
      })
    );
    const { result } = await ready();
    expect(result.current.step).toEqual({ status: 'deferred', means: '[معنى التأجيل]' });
    expect(result.current.finish).toMatchObject({ status: 'done', completion: null });
  });

  it('reads a declared «done» as saved', async () => {
    routes({}, insightOut({ action: { state: 'done', at: null, means: null } }));
    const { result } = await ready();
    expect(result.current.step).toEqual({ status: 'saved' });
  });

  it('says why the insight cannot be read, and reads it again on request', async () => {
    let answered = 0;
    mockApi({
      [`GET /insights/${ID}`]: () => {
        answered += 1;
        return answered === 1 ? apiError(404, 'NOT_FOUND') : { body: insightOut() };
      },
      [`GET /scans/${SCAN}`]: { body: scanOut() },
    });
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.load.phase).toBe('lost'));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.load.phase).toBe('ready'));
  });

  it('drops what arrives after the reader has left', async () => {
    routes();
    const { result, unmount } = renderHook(() => useInsight(ID));
    unmount();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.load.phase).toBe('loading');
    expect(result.current.photo).toBeNull();
  });
});

describe('useInsight: leaving while the photo is asked for', () => {
  it('drops the photo that arrives after the reader has left', async () => {
    let release: () => void = () => undefined;
    routes({
      [`GET /scans/${SCAN}`]: () =>
        new Promise((resolve) => {
          release = () => resolve({ body: scanOut() });
        }),
    });
    const { result, unmount } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.load.phase).toBe('ready'));
    unmount();
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.photo).toBeNull();
  });
});

describe('useInsight: the small step', () => {
  it('records «done» and keeps what the API says it means', async () => {
    routes({
      [`POST /insights/${ID}/action`]: { body: { state: 'done', at: null, means: '[تصريح]' } },
    });
    const { result } = await ready();
    await act(async () => result.current.declare('done'));
    expect(result.current.step).toEqual({ status: 'saved', means: '[تصريح]' });
  });

  it('records «later» as a deferral, with no meaning when the API gives none', async () => {
    routes({
      [`POST /insights/${ID}/action`]: { body: { state: 'later', at: null, means: null } },
    });
    const { result } = await ready();
    await act(async () => result.current.declare('later'));
    expect(result.current.step).toEqual({ status: 'deferred', means: undefined });
  });

  it('keeps the step as it was and says why when the record fails', async () => {
    routes({ [`POST /insights/${ID}/action`]: apiError(503, 'SERVICE_UNAVAILABLE') });
    const { result } = await ready();
    await act(async () => result.current.declare('done'));
    expect(result.current.step.status).toBe('idle');
    expect(result.current.step.error).toContain('جهتنا');
  });

  it('ignores a second tap while one is on its way', async () => {
    let release: () => void = () => undefined;
    const api = routes({
      [`POST /insights/${ID}/action`]: () =>
        new Promise((resolve) => {
          release = () => resolve({ body: { state: 'done', at: null, means: null } });
        }),
    });
    const { result } = await ready();
    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = result.current.declare('done');
      await result.current.declare('done');
    });
    expect(result.current.step.status).toBe('saving');
    release();
    await act(async () => first);
    expect(api.requests.filter((request) => request.url.includes('/action'))).toHaveLength(1);
  });
});

describe('useInsight: «تمّ»', () => {
  it('completes once, then reads the practice to say what was earned', async () => {
    const api = routes({
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': { body: progressOut() },
    });
    const { result } = await ready();
    await act(async () => {
      const first = result.current.complete();
      await result.current.complete();
      await first;
    });
    expect(result.current.finish.status).toBe('done');
    expect(result.current.finish.completion?.place?.name).toBe('واحة الغيث');
    expect(result.current.finish.progress?.daily_quest.done).toBe(true);
    expect(api.requests.filter((request) => request.url.includes('/complete'))).toHaveLength(1);
    const progress = api.requests.find((request) => request.url.includes('/me/progress'));
    expect(new URL(progress?.url as string).searchParams.get('tz')).toBeTruthy();
  });

  it('does not read the practice for a completion that was already recorded', async () => {
    const api = routes({
      [`POST /insights/${ID}/complete`]: { body: completionOut({ first_time: false }) },
    });
    const { result } = await ready();
    await act(async () => result.current.complete());
    expect(result.current.finish).toMatchObject({ status: 'done', progress: null });
    expect(api.requests.some((request) => request.url.includes('/me/progress'))).toBe(false);
  });

  it('says so when the practice cannot be read, and keeps the completion', async () => {
    routes({
      [`POST /insights/${ID}/complete`]: { body: completionOut() },
      'GET /me/progress': apiError(503, 'SERVICE_UNAVAILABLE'),
    });
    const { result } = await ready();
    await act(async () => result.current.complete());
    expect(result.current.finish).toMatchObject({ status: 'done', progressFailed: true });
    expect(result.current.finish.completion).not.toBeNull();
  });

  it('announces nothing and allows another try when the save fails', async () => {
    let answers = 0;
    routes({
      [`POST /insights/${ID}/complete`]: () => {
        answers += 1;
        return answers === 1 ? apiError(503, 'SAVE_FAILED') : { body: completionOut() };
      },
      'GET /me/progress': { body: progressOut() },
    });
    const { result } = await ready();
    await act(async () => result.current.complete());
    expect(result.current.finish.status).toBe('idle');
    expect(result.current.finish.error).toContain('لم تُحفظ البصيرة');
    await act(async () => result.current.complete());
    expect(result.current.finish.status).toBe('done');
    expect(result.current.finish.error).toBeUndefined();
  });
});

describe('useInsight: the chat', () => {
  it('adds the answer and the new count to the insight', async () => {
    routes({ [`POST /insights/${ID}/chat`]: { body: chatReply() } });
    const { result } = await ready();
    let outcome: unknown = 'unset';
    await act(async () => {
      outcome = await result.current.ask('ما معنى هذا؟', 'key-12345678');
    });
    expect(outcome).toBeNull();
    const { load } = result.current;
    const chat = load.phase === 'ready' ? load.insight.chat : null;
    expect(chat).toMatchObject({ used: 1, remaining: 2, limit: 3 });
    expect(chat?.messages).toHaveLength(1);
  });

  it('hands the failure back and changes nothing', async () => {
    routes({ [`POST /insights/${ID}/chat`]: apiError(409, 'CHAT_LIMIT_REACHED') });
    const { result } = await ready();
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.ask('سؤال', 'key-12345678');
    });
    expect(outcome).toMatchObject({ ok: false, code: 'CHAT_LIMIT_REACHED' });
    const { load } = result.current;
    expect(load.phase === 'ready' && load.insight.chat.used).toBe(0);
  });
});

describe('useInsight: publishing', () => {
  it('publishes once at a time, keeps a refusal, and withdraws', async () => {
    const published = {
      insight_id: ID,
      published: true,
      published_at: '2026-10-04T09:00:00Z',
      path: `/insights/${ID}`,
    };
    let answers = 0;
    routes({
      [`PUT /insights/${ID}/publication`]: async () => {
        answers += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return answers === 1 ? { body: published } : apiError(409, 'INSIGHT_NOT_PUBLISHABLE');
      },
      [`DELETE /insights/${ID}/publication`]: {
        body: { insight_id: ID, published: false, published_at: null, path: null },
      },
    });
    const { result } = renderHook(() => useInsight(ID));
    await waitFor(() => expect(result.current.load.phase).toBe('ready'));

    await act(async () => {
      await Promise.all([result.current.publish(), result.current.publish()]);
    });
    expect(answers).toBe(1);
    expect(result.current.publishing).toEqual({ status: 'idle' });
    expect(
      result.current.load.phase === 'ready' ? result.current.load.insight.published_at : null
    ).toBe(published.published_at);

    await act(async () => {
      await result.current.publish();
    });
    expect(result.current.publishing.failure?.status).toBe(409);

    await act(async () => {
      await result.current.withdraw();
    });
    expect(result.current.publishing).toEqual({ status: 'idle' });
    expect(
      result.current.load.phase === 'ready' ? result.current.load.insight.published_at : null
    ).toBeNull();
  });
});
