import { describe, expect, it, vi } from 'vitest';
import { sseBody, sseMessage, sseResponse } from '@/test/scan';
import { isTerminal, parseScanEvent, type ScanEvent } from './events';
import { followEvents, reconnectDelay, waitFor } from './follow';
import { readMessages, type SseMessage, splitMessages } from './sse';

const message = (event: string, data: unknown, id: string | null = '1'): SseMessage => ({
  id,
  event,
  data: JSON.stringify(data),
});

async function collect(body: ReadableStream<Uint8Array>): Promise<SseMessage[]> {
  const out: SseMessage[] = [];
  for await (const item of readMessages(body)) {
    out.push(item);
  }
  return out;
}

describe('splitMessages', () => {
  it('cuts complete messages off and keeps the unfinished rest', () => {
    const { messages, rest } = splitMessages(
      'id: 1\nevent: stage\ndata: {"a":1}\n\nid: 2\ndata: x'
    );
    expect(messages).toEqual([{ id: '1', event: 'stage', data: '{"a":1}' }]);
    expect(rest).toBe('id: 2\ndata: x');
  });

  it('reads \\r\\n and lone \\r line ends, comments, empty fields and several data lines', () => {
    const text = ': ping\r\n\r\nid: 7\revent: done\rdata: a\rdata:b\rdata\r\rtail';
    const { messages, rest } = splitMessages(text);
    expect(messages).toEqual([{ id: '7', event: 'done', data: 'a\nb\n' }]);
    expect(rest).toBe('tail');
  });

  it('keeps a trailing \\r for the next chunk, which may begin with \\n', () => {
    const first = splitMessages('data: a\r\n\r');
    expect(first.messages).toEqual([]);
    expect(first.rest).toBe('data: a\n\r');
    const second = splitMessages(`${first.rest}\n`);
    expect(second.messages).toEqual([{ id: null, event: 'message', data: 'a' }]);
  });

  it('ignores a block with no data, an id with a NUL and a leading empty line', () => {
    const { messages } = splitMessages('event: x\n\n\nid: a\0b\ndata: y\n\n');
    expect(messages).toEqual([{ id: null, event: 'message', data: 'y' }]);
  });
});

describe('readMessages', () => {
  it('yields messages across chunk boundaries, even inside a character', async () => {
    const encoder = new TextEncoder();
    const bytes = encoder.encode('id: 1\ndata: {"t":"مطر"}\n\nid: 2\ndata: {}\n\n');
    const cut = 20;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    expect((await collect(body)).map((item) => item.id)).toEqual(['1', '2']);
    const again = await collect(sseBody([sseMessage(1, 'queued', { run: 1 })]));
    expect(JSON.parse(again[0]?.data as string)).toEqual({ run: 1 });
  });

  it('cancels the body when the reader stops early, and survives a cancel that fails', async () => {
    const cancel = vi.fn(() => Promise.reject(new Error('already closed')));
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: a\n\ndata: b\n\n'));
      },
      cancel,
    });
    for await (const item of readMessages(body)) {
      expect(item.data).toBe('a');
      break;
    }
    expect(cancel).toHaveBeenCalled();
  });
});

describe('parseScanEvent', () => {
  it('reads each kind the API sends', () => {
    expect(parseScanEvent(message('queued', { run: 2 }))).toEqual({ kind: 'queued', run: 2 });
    expect(parseScanEvent(message('done', { run: 1, outcome: 'insights' }))).toEqual({
      kind: 'done',
      run: 1,
    });
    expect(parseScanEvent(message('failed', { run: 1, code: 'VISION_FAILED' }))).toEqual({
      kind: 'failed',
      run: 1,
      code: 'VISION_FAILED',
    });
    expect(parseScanEvent(message('failed', { run: 1, code: null }))).toEqual({
      kind: 'failed',
      run: 1,
      code: '',
    });
    expect(
      parseScanEvent(message('stage', { run: 1, stage: 'verifying', state: 'started' }))
    ).toEqual({ kind: 'stage', run: 1, stage: 'verifying', state: 'started' });
  });

  it('ignores what it does not know instead of guessing', () => {
    expect(parseScanEvent({ id: null, event: 'queued', data: 'not json' })).toBeNull();
    expect(parseScanEvent({ id: null, event: 'queued', data: '3' })).toBeNull();
    expect(parseScanEvent(message('queued', { run: '1' }))).toBeNull();
    expect(
      parseScanEvent(message('stage', { run: 1, stage: 'dreaming', state: 'started' }))
    ).toBeNull();
    expect(
      parseScanEvent(message('stage', { run: 1, stage: 'searching', state: 'maybe' }))
    ).toBeNull();
    expect(parseScanEvent(message('mystery', { run: 1 }))).toBeNull();
  });

  it('knows which events end a run', () => {
    const done: ScanEvent = { kind: 'done', run: 1 };
    const failed: ScanEvent = { kind: 'failed', run: 1, code: '' };
    const queued: ScanEvent = { kind: 'queued', run: 1 };
    expect([done, failed, queued].map(isTerminal)).toEqual([true, true, false]);
  });
});

describe('followEvents', () => {
  const noWait = () => Promise.resolve();

  it('reads events until one ends the run, and reports the last event number', async () => {
    const seen: string[] = [];
    const followed = await followEvents({
      open: async () =>
        sseResponse([sseMessage(1, 'queued', { run: 1 }), sseMessage(2, 'done', { run: 1 })]),
      handle: (item) => {
        seen.push(item.event);
        return item.event === 'done';
      },
      signal: new AbortController().signal,
      wait: noWait,
    });
    expect(followed).toEqual({ end: 'terminal', lastEventId: '2' });
    expect(seen).toEqual(['queued', 'done']);
  });

  it('resumes after a drop with Last-Event-ID, so nothing is missed or repeated', async () => {
    const asked: Array<string | null> = [];
    const responses = [
      () => sseResponse([sseMessage(4, 'stage', { run: 1, stage: 'searching', state: 'started' })]),
      () => {
        throw new TypeError('connection lost');
      },
      () => sseResponse([sseMessage(5, 'done', { run: 1 })]),
    ];
    const followed = await followEvents({
      open: async (last) => {
        asked.push(last);
        return (responses.shift() as () => Response)();
      },
      handle: (item) => item.event === 'done',
      signal: new AbortController().signal,
      after: '3',
      wait: noWait,
    });
    expect(asked).toEqual(['3', '4', '4']);
    expect(followed).toEqual({ end: 'terminal', lastEventId: '5' });
  });

  it('keeps the last number when a message has none', async () => {
    const followed = await followEvents({
      open: async () => sseResponse(['data: {"run":1}\n\n']),
      handle: () => true,
      signal: new AbortController().signal,
      after: '9',
      wait: noWait,
    });
    expect(followed.lastEventId).toBe('9');
  });

  it('gives up after repeated failures, and at once on a refusal that will not change', async () => {
    const open = vi.fn(async () => new Response(null, { status: 503 }));
    const failing = await followEvents({
      open,
      handle: () => false,
      signal: new AbortController().signal,
      wait: noWait,
      maxFailures: 3,
    });
    expect(failing.end).toBe('gave-up');
    expect(open).toHaveBeenCalledTimes(3);

    const refused = vi.fn(async () => new Response(null, { status: 404 }));
    const notFound = await followEvents({
      open: refused,
      handle: () => false,
      signal: new AbortController().signal,
      wait: noWait,
    });
    expect(notFound.end).toBe('gave-up');
    expect(refused).toHaveBeenCalledTimes(1);

    const bodyless = await followEvents({
      open: async () => new Response(null, { status: 200 }),
      handle: () => false,
      signal: new AbortController().signal,
      wait: noWait,
      maxFailures: 1,
    });
    expect(bodyless.end).toBe('gave-up');
  });

  it('retries a 429 and a 408 like any other drop', async () => {
    const statuses = [429, 408, 200];
    const followed = await followEvents({
      open: async () => {
        const status = statuses.shift() as number;
        return status === 200
          ? sseResponse([sseMessage(1, 'done', { run: 1 })])
          : new Response(null, { status });
      },
      handle: () => true,
      signal: new AbortController().signal,
      wait: noWait,
    });
    expect(followed.end).toBe('terminal');
  });

  it('opens a stream the server closed without an end again, after a pause', async () => {
    const waits: number[] = [];
    let opened = 0;
    const followed = await followEvents({
      open: async () => {
        opened += 1;
        return opened === 1 ? sseResponse([]) : sseResponse([sseMessage(1, 'done', { run: 1 })]);
      },
      handle: () => true,
      signal: new AbortController().signal,
      wait: async (milliseconds) => {
        waits.push(milliseconds);
      },
    });
    expect(waits).toEqual([1000]);
    expect(followed.end).toBe('terminal');
  });

  it('stops when the reader leaves, whether before, during or after a request', async () => {
    const before = new AbortController();
    before.abort();
    expect(
      (await followEvents({ open: vi.fn(), handle: () => false, signal: before.signal })).end
    ).toBe('aborted');

    const during = new AbortController();
    const followed = await followEvents({
      open: async () => {
        during.abort();
        throw new DOMException('aborted', 'AbortError');
      },
      handle: () => false,
      signal: during.signal,
      wait: noWait,
    });
    expect(followed.end).toBe('aborted');

    const waiting = new AbortController();
    const afterWait = await followEvents({
      open: async () => sseResponse([]),
      handle: () => false,
      signal: waiting.signal,
      wait: async () => waiting.abort(),
    });
    expect(afterWait.end).toBe('aborted');
  });
});

describe('reconnectDelay and waitFor', () => {
  it('waits a second at least, doubles, and stops growing at fifteen seconds', () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(reconnectDelay)).toEqual([
      1000, 2000, 4000, 8000, 15_000, 15_000, 15_000,
    ]);
  });

  it('waits the time given, or ends at once when the reader leaves', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const waited = vi.fn();
    waitFor(500, controller.signal).then(waited);
    await vi.advanceTimersByTimeAsync(499);
    expect(waited).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(waited).toHaveBeenCalled();

    const early = new AbortController();
    const ended = vi.fn();
    waitFor(60_000, early.signal).then(ended);
    early.abort();
    await vi.advanceTimersByTimeAsync(0);
    expect(ended).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
