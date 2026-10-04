import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchAccountEmail, sendSupport } from './support';

const REQUEST = {
  email: 'a@b.co',
  topic: 'bug',
  message: 'x'.repeat(20),
  website: '',
} as const;

function answer(status: number, body?: unknown) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response(body === undefined ? null : JSON.stringify(body), { status }));
}

afterEach(() => vi.restoreAllMocks());

describe('sendSupport', () => {
  it('posts the form, honeypot included, with credentials', async () => {
    const spy = answer(202);
    expect(await sendSupport(REQUEST)).toBe('sent');
    const [url, init] = spy.mock.calls[0] ?? [];
    expect(url).toBe('https://api.tabsira.test/support');
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(JSON.parse(String(init?.body))).toEqual(REQUEST);
  });

  it.each([
    [422, 'invalid'],
    [429, 'rate_limited'],
    [503, 'mail_unavailable'],
    [500, 'failed'],
    [200, 'failed'],
  ])('maps %i to %s, and only 202 is sent', async (status, outcome) => {
    answer(status, { code: 'mail_unavailable' });
    expect(await sendSupport(REQUEST)).toBe(outcome);
  });

  it('is failed, not sent, when the network is down', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'));
    expect(await sendSupport(REQUEST)).toBe('failed');
  });
});

describe('fetchAccountEmail', () => {
  it('returns the signed-in address', async () => {
    const spy = answer(200, { email: 'me@x.co' });
    expect(await fetchAccountEmail()).toBe('me@x.co');
    expect(spy.mock.calls[0]?.[0]).toBe('https://api.tabsira.test/auth/me');
    expect(spy.mock.calls[0]?.[1]).toMatchObject({ credentials: 'include' });
  });

  it.each([
    ['signed out', () => answer(401, { error: 'x' })],
    ['an account without an address', () => answer(200, { id: 1 })],
    ['a body that is not an object', () => answer(200, 'text')],
    ['an address that is not text', () => answer(200, { email: 3 })],
    ['null', () => answer(200, null)],
    ['no network', () => vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('x'))],
  ])('returns nothing for %s', async (_case, arrange) => {
    arrange();
    expect(await fetchAccountEmail()).toBeUndefined();
  });
});
