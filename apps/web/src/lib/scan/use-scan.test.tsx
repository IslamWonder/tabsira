import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scanOut, sseMessage } from '@/test/scan';
import { POLL_EVERY_MS, SLOW_AFTER_MS, useScan } from './use-scan';

const ID = '110000000000000001';
const encoder = new TextEncoder();

/** A stream the test writes to by hand, as the API writes to a live connection. */
function liveStream() {
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    /** What fetch answers; the body fails when the reader aborts, as a real connection does. */
    open: (signal?: AbortSignal | null) => {
      signal?.addEventListener('abort', () =>
        controller?.error(new DOMException('', 'AbortError'))
      );
      return new Response(body, { status: 200 });
    },
    push: (chunk: string) => controller?.enqueue(encoder.encode(chunk)),
    end: () => controller?.close(),
  };
}

interface Server {
  /** What GET /scans/{id} answers, one entry per call; the last one repeats. */
  scans: Array<() => Response | Promise<Response>>;
  /** What the stream answers, one entry per opening; the last one repeats. */
  streams: Array<(signal?: AbortSignal | null) => Response>;
  posts: Record<string, () => Response>;
  opened: Array<string | null>;
  reads: number;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function next<T>(queue: T[]): T {
  return (queue.length > 1 ? queue.shift() : queue[0]) as T;
}

function serve(server: Partial<Server>): Server {
  const state: Server = { scans: [], streams: [], posts: {}, opened: [], reads: 0, ...server };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (typeof input === 'string') {
        state.opened.push(new Headers(init?.headers).get('Last-Event-ID'));
        return next(state.streams)(init?.signal);
      }
      const request = input as Request;
      if (request.method === 'GET') {
        state.reads += 1;
        return next(state.scans)();
      }
      return (state.posts[new URL(request.url).pathname] as () => Response)();
    })
  );
  return state;
}

const running =
  (run = 1) =>
  () =>
    json(scanOut({ status: 'running', outcome: null, run, insights: [], finished_at: null }));
const done =
  (run = 1) =>
  () =>
    json(scanOut({ run }));
const gone = () => json({ error: 'NOT_FOUND', detail: 'x' }, 404);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
});
afterEach(() => {
  vi.useRealTimers();
});

async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useScan: reading', () => {
  it('shows a finished scan as ready, without opening a stream', async () => {
    const server = serve({ scans: [done()] });
    const { result } = renderHook(() => useScan(ID));
    expect(result.current.view.phase).toBe('loading');
    await tick();
    expect(result.current.view).toMatchObject({ phase: 'ready' });
    expect(server.opened).toEqual([]);
  });

  it('shows a failed scan with its code', async () => {
    serve({
      scans: [
        () => json(scanOut({ status: 'failed', outcome: null, error_code: 'VISION_FAILED' })),
      ],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    expect(result.current.view).toMatchObject({ phase: 'failed', code: 'VISION_FAILED' });
  });

  it('says so when the scan cannot be read, and reads it again on request', async () => {
    serve({ scans: [gone, done()] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    expect(result.current.view).toMatchObject({ phase: 'lost', failure: { code: 'NOT_FOUND' } });
    act(() => result.current.reload());
    await tick();
    expect(result.current.view.phase).toBe('ready');
  });

  it('drops the answer of a read the reader has left behind', async () => {
    serve({ scans: [done()] });
    const { result, unmount } = renderHook(() => useScan(ID));
    unmount();
    await tick();
    expect(result.current.view.phase).toBe('loading');
  });
});

describe('useScan: following a run', () => {
  it('shows the stages as the server reports them, then the result', async () => {
    const live = liveStream();
    serve({ scans: [running(), done()], streams: [(signal) => live.open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    expect(result.current.view.phase).toBe('running');
    expect(result.current.stage).toBe('queued');

    await act(async () => {
      live.push(sseMessage(1, 'queued', { run: 1 }));
      live.push(sseMessage(2, 'stage', { run: 1, stage: 'understanding', state: 'started' }));
    });
    await tick();
    expect(result.current.stage).toBe('understanding');

    await act(async () => {
      live.push(sseMessage(3, 'stage', { run: 1, stage: 'understanding', state: 'failed' }));
      live.push(sseMessage(4, 'stage', { run: 1, stage: 'searching', state: 'started' }));
      live.push('data: {"run":1}\n\nid: 5\nevent: mystery\ndata: {"run":1}\n\n');
    });
    await tick();
    expect(result.current.stage).toBe('searching');
    expect(result.current.sound).toBeNull();

    await act(async () => {
      live.push(sseMessage(6, 'sound', { run: 1, url: '/sounds/ontology/E006' }));
    });
    await tick();
    expect(result.current.sound).toBe('/sounds/ontology/E006');
    expect(result.current.stage).toBe('searching');

    await act(async () => {
      live.push(sseMessage(7, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('ready');
    // The sound stays known while its last loop plays.
    expect(result.current.sound).toBe('/sounds/ontology/E006');
  });

  it('reads the scan again once the scene is understood, to show its photo, without losing the stage', async () => {
    const live = liveStream();
    const withPhoto = () =>
      json(scanOut({ status: 'running', outcome: null, insights: [], finished_at: null }));
    const server = serve({
      scans: [running(), withPhoto],
      streams: [(signal) => live.open(signal)],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'stage', { run: 1, stage: 'searching', state: 'started' }));
      live.push(sseMessage(2, 'stage', { run: 1, stage: 'understanding', state: 'done' }));
    });
    await tick();
    expect(server.reads).toBe(2);
    const view = result.current.view;
    expect(result.current.stage).toBe('searching');
    expect(view.phase === 'running' && view.scan.image.available).toBe(true);
  });

  it('ends on a failed run with the code of the scan', async () => {
    const live = liveStream();
    serve({
      scans: [
        running(),
        () => json(scanOut({ status: 'failed', outcome: null, error_code: 'SOURCE_UNAVAILABLE' })),
      ],
      streams: [(signal) => live.open(signal)],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'failed', { run: 1, code: 'SOURCE_UNAVAILABLE' }));
    });
    await tick();
    expect(result.current.view).toMatchObject({ phase: 'failed', code: 'SOURCE_UNAVAILABLE' });
  });

  it('resumes after a dropped connection with Last-Event-ID', async () => {
    const first = liveStream();
    const second = liveStream();
    const server = serve({
      scans: [running(), done()],
      streams: [(signal) => first.open(signal), (signal) => second.open(signal)],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      first.push(sseMessage(7, 'stage', { run: 1, stage: 'verifying', state: 'started' }));
    });
    await tick();
    await act(async () => first.end());
    await tick(1000);
    expect(server.opened).toEqual([null, '7']);
    await act(async () => {
      second.push(sseMessage(8, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('ready');
  });

  it('ignores the events of an earlier run', async () => {
    const live = liveStream();
    serve({ scans: [running(2), done(2)], streams: [(signal) => live.open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'stage', { run: 1, stage: 'composing', state: 'started' }));
      live.push(sseMessage(2, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('running');
    expect(result.current.stage).toBe('queued');
    await act(async () => {
      live.push(sseMessage(3, 'done', { run: 2, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('ready');
  });

  it('asks for the scan itself when the stream cannot be kept, until the run ends', async () => {
    const server = serve({
      scans: [running(), running(), done()],
      streams: [() => new Response(null, { status: 503 })],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    // Five failed openings, with pauses of 2, 4, 8 and 15 seconds, then the polling begins.
    await tick(2000 + 4000 + 8000 + 15_000);
    expect(server.opened).toHaveLength(5);
    expect(result.current.view.phase).toBe('running');
    await tick(POLL_EVERY_MS);
    expect(result.current.view.phase).toBe('running');
    await tick(POLL_EVERY_MS);
    expect(result.current.view.phase).toBe('ready');
  });

  it('keeps polling through a dropped network and gives the scan up when it is gone', async () => {
    serve({
      scans: [
        running(),
        () => {
          throw new TypeError('offline');
        },
        gone,
      ],
      streams: [() => new Response(null, { status: 403 })],
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await tick(POLL_EVERY_MS);
    expect(result.current.view.phase).toBe('running');
    await tick(POLL_EVERY_MS);
    expect(result.current.view).toMatchObject({ phase: 'lost', failure: { code: 'NOT_FOUND' } });
  });

  it('polls when the run ended but the scan still says it is running', async () => {
    const live = liveStream();
    serve({ scans: [running(), running(), done()], streams: [(signal) => live.open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('running');
    await tick(POLL_EVERY_MS);
    expect(result.current.view.phase).toBe('ready');
  });

  it('says the scan is lost when it cannot be read after the run ended', async () => {
    const live = liveStream();
    serve({ scans: [running(), gone], streams: [(signal) => live.open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('lost');
  });

  it('says calmly that it is taking longer, and only while it runs', async () => {
    serve({ scans: [running()], streams: [(signal) => liveStream().open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await tick(SLOW_AFTER_MS);
    expect(result.current.view.phase).toBe('running');
    expect(result.current.slow).toBe(true);
  });

  it('does not mark a finished scan as slow', async () => {
    serve({ scans: [done()] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await tick(SLOW_AFTER_MS);
    expect(result.current.view.phase).toBe('ready');
  });

  it('stops everything when the reader leaves', async () => {
    const live = liveStream();
    const server = serve({ scans: [running()], streams: [(signal) => live.open(signal)] });
    const { unmount } = renderHook(() => useScan(ID));
    await tick();
    unmount();
    await tick(POLL_EVERY_MS * 3);
    expect(server.opened).toHaveLength(1);
  });
});

describe('useScan: late answers', () => {
  const deferred = () => {
    let release: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    return { pending, release: () => release(done()()) };
  };

  it('drops a read that is older than the run on screen', async () => {
    const live = liveStream();
    serve({ scans: [running(2), running(1)], streams: [(signal) => live.open(signal)] });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'stage', { run: 2, stage: 'understanding', state: 'done' }));
    });
    await tick();
    const view = result.current.view;
    expect(view.phase === 'running' && view.scan.run).toBe(2);
  });

  it('drops the read that ends a run when the reader has left meanwhile', async () => {
    const late = deferred();
    const live = liveStream();
    serve({ scans: [running(), () => late.pending], streams: [(signal) => live.open(signal)] });
    const { result, unmount } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      live.push(sseMessage(1, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    unmount();
    late.release();
    await tick();
    expect(result.current.view.phase).toBe('running');
  });

  it('stops polling when the reader leaves, while waiting or while asking', async () => {
    const late = deferred();
    serve({
      scans: [running(), running(), () => late.pending],
      streams: [() => new Response(null, { status: 403 })],
    });
    const waiting = renderHook(() => useScan(ID));
    await tick();
    waiting.unmount();
    await tick(POLL_EVERY_MS);

    const asking = renderHook(() => useScan(ID));
    await tick();
    await tick(POLL_EVERY_MS);
    asking.unmount();
    late.release();
    await tick();
    expect(asking.result.current.view.phase).toBe('running');
  });
});

describe('useScan: focus and clarification', () => {
  it('looks again at one thing: a new run begins, and its stream resumes after the last number', async () => {
    const first = liveStream();
    const second = liveStream();
    const server = serve({
      scans: [running(), done(), done(2)],
      streams: [(signal) => first.open(signal), (signal) => second.open(signal)],
      posts: {
        [`/scans/${ID}/focus`]: () =>
          json(scanOut({ status: 'queued', outcome: null, run: 2, insights: [] }), 202),
      },
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      first.push(sseMessage(5, 'done', { run: 1, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view.phase).toBe('ready');

    let outcome: unknown = 'unset';
    await act(async () => {
      outcome = await result.current.focus('e1');
    });
    expect(outcome).toBeNull();
    expect(result.current.view.phase).toBe('running');
    expect(result.current.stage).toBe('queued');
    expect(result.current.acting).toBe(false);
    await tick();
    expect(server.opened).toEqual([null, '5']);
    await act(async () => {
      second.push(sseMessage(6, 'done', { run: 2, outcome: 'insights' }));
    });
    await tick();
    expect(result.current.view).toMatchObject({ phase: 'ready' });
  });

  it('answers the question the same way', async () => {
    serve({
      scans: [
        () => json(scanOut({ outcome: 'needs_clarification', clarification_question: 'ما تقصد؟' })),
        running(2),
      ],
      streams: [(signal) => liveStream().open(signal)],
      posts: {
        [`/scans/${ID}/clarify`]: () =>
          json(scanOut({ status: 'queued', outcome: null, run: 2, insights: [] }), 202),
      },
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    await act(async () => {
      await result.current.clarify('جواب');
    });
    expect(result.current.view).toMatchObject({ phase: 'running' });
  });

  it('returns the failure and keeps the scan as it was when the API refuses', async () => {
    serve({
      scans: [done()],
      posts: { [`/scans/${ID}/focus`]: () => json({ error: 'SCAN_BUSY', detail: 'x' }, 409) },
    });
    const { result } = renderHook(() => useScan(ID));
    await tick();
    let outcome: unknown;
    await act(async () => {
      outcome = await result.current.focus('e1');
    });
    expect(outcome).toMatchObject({ ok: false, code: 'SCAN_BUSY' });
    expect(result.current.view.phase).toBe('ready');
    expect(result.current.acting).toBe(false);
  });
});
