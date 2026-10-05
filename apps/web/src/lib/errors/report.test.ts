import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  FLUSH_DELAY_MS,
  flushErrors,
  installErrorReporting,
  MAX_BATCH,
  MAX_PER_PAGE,
  reportError,
  resetErrorReporting,
} from './report';

type Sent = { items: Record<string, unknown>[] };

let fetch: ReturnType<typeof vi.fn>;
const bodies = (): Sent[] =>
  fetch.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string) as Sent);

beforeEach(() => {
  resetErrorReporting();
  vi.useFakeTimers();
  fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetch);
  window.history.replaceState(null, '', '/insight/42?token=secret#part');
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('reportError', () => {
  it('batches errors and posts them to the API without a cookie, the query or the fragment', () => {
    const error = new TypeError('x is not a function');
    reportError(error);
    reportError('a plain message', { handled: false });
    expect(fetch).not.toHaveBeenCalled();
    vi.advanceTimersByTime(FLUSH_DELAY_MS);

    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/client-errors$/);
    expect(init).toMatchObject({ method: 'POST', keepalive: true, credentials: 'omit' });
    const [first, second] = bodies()[0]?.items ?? [];
    expect(first).toMatchObject({
      kind: 'error',
      level: 'error',
      message: 'x is not a function',
      name: 'TypeError',
      handled: true,
      url: `${window.location.origin}/insight/42`,
    });
    expect(String(first?.stack)).toContain('TypeError');
    expect(second).toMatchObject({ message: 'a plain message', level: 'fatal', handled: false });
    expect(second).not.toHaveProperty('name');
  });

  it('sends the same error once, a full batch at once, and stops after a page load’s worth', () => {
    const same = new Error('same');
    reportError(same);
    reportError(same);
    for (let n = 1; n < MAX_BATCH; n += 1) {
      reportError(new Error(`error ${n}`));
    }
    expect(bodies()[0]?.items).toHaveLength(MAX_BATCH);
    for (let n = 0; n < MAX_PER_PAGE * 2; n += 1) {
      reportError(new Error(`more ${n}`));
    }
    vi.advanceTimersByTime(FLUSH_DELAY_MS);
    const total = bodies().reduce((count, body) => count + body.items.length, 0);
    expect(total).toBe(MAX_PER_PAGE);
  });

  it('names an unknown throw, keeps a bad type name out, and bounds message and stack', () => {
    reportError({ not: 'an error' });
    const odd = new Error('x'.repeat(5000));
    odd.name = 'Not an identifier!';
    odd.stack = 's'.repeat(20_000);
    reportError(odd);
    const empty = new RangeError('');
    empty.stack = '';
    reportError(empty);
    flushErrors();
    const [unknown, bounded, unnamed] = bodies()[0]?.items ?? [];
    expect(unknown?.message).toBe('Unknown error');
    expect(bounded).not.toHaveProperty('name');
    expect(String(bounded?.message)).toHaveLength(2000);
    expect(String(bounded?.stack)).toHaveLength(16_000);
    expect(unnamed).toMatchObject({ message: 'RangeError', name: 'RangeError' });
    expect(unnamed).not.toHaveProperty('stack');
  });

  it('a reset drops what was waiting to be sent', () => {
    reportError(new Error('pending'));
    resetErrorReporting();
    vi.advanceTimersByTime(FLUSH_DELAY_MS);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('never throws, whatever the network does', () => {
    fetch.mockRejectedValueOnce(new TypeError('offline'));
    reportError(new Error('one'));
    expect(() => flushErrors()).not.toThrow();
    vi.stubGlobal('fetch', () => {
      throw new Error('no fetch');
    });
    reportError(new Error('two'));
    expect(() => flushErrors()).not.toThrow();
    flushErrors();
  });
});

describe('installErrorReporting', () => {
  it('reports uncaught errors and rejections once, and sends when the page is hidden', () => {
    installErrorReporting();
    installErrorReporting();
    window.dispatchEvent(new ErrorEvent('error', { error: new Error('boom'), message: 'boom' }));
    window.dispatchEvent(new ErrorEvent('error', { message: 'Script error.' }));
    // A resource that failed to load: no error and no message.
    window.dispatchEvent(new ErrorEvent('error', {}));
    const rejection = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(rejection, 'reason', { value: new Error('rejected') });
    window.dispatchEvent(rejection);

    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    document.dispatchEvent(new Event('visibilitychange'));
    expect(fetch).not.toHaveBeenCalled();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange'));

    expect(bodies()[0]?.items.map((item) => item.message)).toEqual([
      'boom',
      'Script error.',
      'rejected',
    ]);
    expect(bodies()[0]?.items.every((item) => item.handled === false)).toBe(true);
  });
});
