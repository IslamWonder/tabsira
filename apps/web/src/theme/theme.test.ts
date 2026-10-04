import { afterEach, describe, expect, it, vi } from 'vitest';
import { THEME_BACKGROUND } from './colors';
import {
  applyThemePreference,
  readThemePreference,
  setThemePreference,
  subscribeThemePreference,
  THEME_STORAGE_KEY,
} from './theme';

function addThemeColorMetas() {
  for (const media of ['(prefers-color-scheme: light)', '(prefers-color-scheme: dark)']) {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.media = media;
    document.head.append(meta);
  }
  return Array.from(document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]'));
}

afterEach(() => {
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
    meta.remove();
  }
});

describe('theme preference', () => {
  it('reads system when nothing valid is stored', () => {
    expect(readThemePreference()).toBe('system');
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    expect(readThemePreference()).toBe('system');
  });

  it('reads system when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readThemePreference()).toBe('system');
  });

  it('stores, applies and announces a choice', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeThemePreference(listener);
    setThemePreference('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(readThemePreference()).toBe('light');
    setThemePreference('system');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    setThemePreference('dark');
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('still applies the choice for this visit when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setThemePreference('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('follows a change made in another tab', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeThemePreference(listener);
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'something.else' }));
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('points the status bar colour at the chosen theme, and back at the device', () => {
    const [lightMeta, darkMeta] = addThemeColorMetas();
    applyThemePreference('dark');
    expect(lightMeta?.content).toBe(THEME_BACKGROUND.dark);
    expect(darkMeta?.content).toBe(THEME_BACKGROUND.dark);
    applyThemePreference('system');
    expect(lightMeta?.content).toBe(THEME_BACKGROUND.light);
    expect(darkMeta?.content).toBe(THEME_BACKGROUND.dark);
  });
});
