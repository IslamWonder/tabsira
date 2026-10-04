import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TURNSTILE_WAIT_MS } from '@/lib/turnstile';
import { type UseTurnstile, useTurnstile } from './use-turnstile';

const loader = vi.hoisted(() => ({ load: vi.fn<() => Promise<void>>() }));
vi.mock('@/lib/turnstile', async (original) => ({
  ...(await original<typeof import('@/lib/turnstile')>()),
  loadTurnstile: loader.load,
}));

const KEY = '1x00000000000000000000AA';

interface Fake {
  api: TurnstileApi;
  render: ReturnType<typeof vi.fn<TurnstileApi['render']>>;
  reset: ReturnType<typeof vi.fn<TurnstileApi['reset']>>;
  remove: ReturnType<typeof vi.fn<TurnstileApi['remove']>>;
  options: () => TurnstileRenderOptions;
}

function fakeApi(): Fake {
  const renderFn = vi.fn<TurnstileApi['render']>(() => 'w1');
  const reset = vi.fn<TurnstileApi['reset']>();
  const remove = vi.fn<TurnstileApi['remove']>();
  return {
    api: { render: renderFn, reset, remove },
    render: renderFn,
    reset,
    remove,
    options: () => renderFn.mock.calls[0]?.[1] as TurnstileRenderOptions,
  };
}

let fake: Fake;
let current: UseTurnstile;

function Harness({ siteKey }: { siteKey: string }) {
  current = useTurnstile(siteKey);
  return <form>{current.widget}</form>;
}

async function mount(siteKey = KEY, drawn = true) {
  const view = render(<Harness siteKey={siteKey} />);
  if (siteKey !== '' && drawn) {
    await waitFor(() => expect(fake.render).toHaveBeenCalled());
  }
  return view;
}

beforeEach(() => {
  fake = fakeApi();
  window.turnstile = fake.api;
  loader.load.mockResolvedValue(undefined);
});

afterEach(() => {
  delete window.turnstile;
  delete document.documentElement.dataset.theme;
  vi.useRealTimers();
});

describe('useTurnstile with no site key', () => {
  it('renders nothing, loads nothing and sends no header', async () => {
    const { container } = await mount('');
    expect(current.widget).toBeNull();
    expect(container.querySelector('fieldset')).toBeNull();
    expect(loader.load).not.toHaveBeenCalled();
    await expect(current.headers()).resolves.toEqual({});
    expect(() => current.reset()).not.toThrow();
  });
});

describe('useTurnstile with a site key', () => {
  it('loads the script and draws the widget in Arabic, in a labelled place that keeps its room', async () => {
    await mount();
    expect(loader.load).toHaveBeenCalledTimes(1);
    expect(fake.options()).toMatchObject({ sitekey: KEY, language: 'ar', theme: 'auto' });
    expect(screen.getByRole('group', { name: 'التحقق من أنك لست برنامجًا آليًا' })).toBeVisible();
    expect(document.querySelector('.min-h-\\[65px\\]')).not.toBeNull();
  });

  it('follows the theme the reader chose in the app', async () => {
    document.documentElement.dataset.theme = 'dark';
    await mount();
    expect(fake.options().theme).toBe('dark');
  });

  it('uses the compact box where the form is narrower than the flexible one, and keeps its room', async () => {
    await mount();
    expect(fake.options().size).toBe('compact');
    expect(document.querySelector<HTMLElement>('fieldset > div')?.style.minHeight).toBe('140px');
  });

  it('uses the flexible box where there is room', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(340);
    await mount();
    expect(fake.options().size).toBe('flexible');
    expect(document.querySelector<HTMLElement>('fieldset > div')?.style.minHeight).toBe('');
  });

  it('sends the token in the one header, and asks for a fresh one after the submit', async () => {
    await mount();
    act(() => fake.options().callback?.('tok-1'));
    await expect(current.headers()).resolves.toEqual({ 'CF-Turnstile-Response': 'tok-1' });
    current.reset();
    expect(fake.reset).toHaveBeenCalledWith('w1');
    // A spent token is never offered again: the next submit waits for the new one.
    vi.useFakeTimers();
    const next = current.headers();
    act(() => fake.options().callback?.('tok-2'));
    await expect(next).resolves.toEqual({ 'CF-Turnstile-Response': 'tok-2' });
  });

  it('waits for a check that is still running, then goes without a token', async () => {
    await mount();
    vi.useFakeTimers();
    const waiting = current.headers();
    await vi.advanceTimersByTimeAsync(TURNSTILE_WAIT_MS);
    await expect(waiting).resolves.toEqual({});
  });

  it('stops waiting when the check reports an error, and does not wait again', async () => {
    await mount();
    const waiting = current.headers();
    act(() => fake.options()['error-callback']?.());
    await expect(waiting).resolves.toEqual({});
    await expect(current.headers()).resolves.toEqual({});
  });

  it('takes a token again after an error once the check recovers', async () => {
    await mount();
    act(() => fake.options()['error-callback']?.());
    act(() => fake.options().callback?.('tok-3'));
    await expect(current.headers()).resolves.toEqual({ 'CF-Turnstile-Response': 'tok-3' });
  });

  it('drops an expired token and resets the widget for a new one', async () => {
    await mount();
    act(() => fake.options().callback?.('tok-1'));
    act(() => fake.options()['expired-callback']?.());
    expect(fake.reset).toHaveBeenCalledWith('w1');
    vi.useFakeTimers();
    const waiting = current.headers();
    await vi.advanceTimersByTimeAsync(TURNSTILE_WAIT_MS);
    await expect(waiting).resolves.toEqual({});
  });

  it('lets the form submit, with no header, when the script cannot load', async () => {
    loader.load.mockRejectedValue(new Error('blocked'));
    await mount(KEY, false);
    await waitFor(() => expect(loader.load).toHaveBeenCalled());
    await expect(current.headers()).resolves.toEqual({});
    expect(fake.render).not.toHaveBeenCalled();
  });

  it('removes the widget when the form goes away', async () => {
    const { unmount } = await mount();
    unmount();
    expect(fake.remove).toHaveBeenCalledWith('w1');
  });

  it('draws nothing when the form went away before the script loaded', async () => {
    let finish: () => void = () => undefined;
    loader.load.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    const { unmount } = await mount(KEY, false);
    unmount();
    await act(async () => finish());
    expect(fake.render).not.toHaveBeenCalled();
    expect(fake.remove).not.toHaveBeenCalled();
  });

  it('does not report a failed load after the form went away', async () => {
    let fail: (error: Error) => void = () => undefined;
    loader.load.mockReturnValue(new Promise<void>((_, reject) => (fail = reject)));
    const { unmount } = await mount(KEY, false);
    unmount();
    await act(async () => fail(new Error('blocked')));
    expect(fake.render).not.toHaveBeenCalled();
  });
});
