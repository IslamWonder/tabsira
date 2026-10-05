import { describe, expect, it, vi } from 'vitest';
import { OWN_INSIGHT_KEY } from '@/account/own-insight';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { PREFERENCES_INIT_SCRIPT } from './init-script';
import { MOTION_STORAGE_KEY } from './motion';

function run() {
  // The exact string <head> runs before the first paint.
  new Function(PREFERENCES_INIT_SCRIPT)();
}

describe('the inline preferences script', () => {
  it('applies a stored explicit theme and a motion opt-out', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    window.localStorage.setItem(MOTION_STORAGE_KEY, 'off');
    run();
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.dataset.motion).toBe('reduce');
  });

  it('marks the page for the home capture when the account last seen held its own insight', () => {
    window.localStorage.setItem(OWN_INSIGHT_KEY, '1');
    run();
    expect(document.documentElement.hasAttribute('data-own-insight')).toBe(true);
    document.documentElement.removeAttribute('data-own-insight');
    window.localStorage.removeItem(OWN_INSIGHT_KEY);
  });

  it('leaves the device in charge otherwise', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    run();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(document.documentElement.hasAttribute('data-motion')).toBe(false);
    expect(document.documentElement.hasAttribute('data-own-insight')).toBe(false);
  });

  it('survives blocked storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(run).not.toThrow();
  });
});
