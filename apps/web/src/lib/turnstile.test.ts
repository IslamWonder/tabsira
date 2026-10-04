import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Loader = typeof import('./turnstile');

/** A fresh module each time: the loader remembers its pending load for the life of the page. */
async function freshModule(): Promise<Loader> {
  vi.resetModules();
  return import('./turnstile');
}

function scripts(): HTMLScriptElement[] {
  return [...document.head.querySelectorAll<HTMLScriptElement>('script')];
}

beforeEach(() => {
  delete window.turnstile;
});

afterEach(() => {
  for (const script of scripts()) {
    script.remove();
  }
  delete window.turnstile;
});

describe('loadTurnstile', () => {
  it('loads the script once however many forms ask, and resolves when it loads', async () => {
    const { loadTurnstile, TURNSTILE_SCRIPT } = await freshModule();
    const first = loadTurnstile();
    const second = loadTurnstile();
    expect(scripts()).toHaveLength(1);
    expect(scripts()[0]).toHaveAttribute('src', TURNSTILE_SCRIPT);
    expect(TURNSTILE_SCRIPT).toBe(
      'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    );
    scripts()[0]?.onload?.(new Event('load'));
    await expect(Promise.all([first, second])).resolves.toEqual([undefined, undefined]);
  });

  it('adds nothing when the API is already on the page', async () => {
    const { loadTurnstile } = await freshModule();
    window.turnstile = { render: vi.fn(), reset: vi.fn(), remove: vi.fn() };
    await expect(loadTurnstile()).resolves.toBeUndefined();
    expect(scripts()).toHaveLength(0);
  });

  it('rejects when the script cannot load, and lets a later form try again', async () => {
    const { loadTurnstile } = await freshModule();
    const failed = loadTurnstile();
    scripts()[0]?.onerror?.(new Event('error'));
    await expect(failed).rejects.toThrow('turnstile script failed to load');
    const again = loadTurnstile();
    expect(scripts()).toHaveLength(2);
    scripts()[1]?.onload?.(new Event('load'));
    await expect(again).resolves.toBeUndefined();
  });
});

describe('turnstileHeaders', () => {
  it('names the one header, and sends none without a token', async () => {
    const { turnstileHeaders, TURNSTILE_HEADER } = await freshModule();
    expect(TURNSTILE_HEADER).toBe('CF-Turnstile-Response');
    expect(turnstileHeaders('tok')).toEqual({ 'CF-Turnstile-Response': 'tok' });
    expect(turnstileHeaders(null)).toEqual({});
  });
});
