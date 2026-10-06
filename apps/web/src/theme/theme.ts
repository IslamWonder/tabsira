import { THEME_BACKGROUND } from './colors';

/**
 * Theme preference, stored per device. `system` follows prefers-color-scheme
 * through CSS alone; `light` and `dark` set data-theme on <html>.
 */
export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_PREFERENCES: readonly ThemePreference[] = ['system', 'light', 'dark'];
export const THEME_STORAGE_KEY = 'tabsira.theme';
const CHANGE_EVENT = 'tabsira:theme-change';

function isExplicit(value: unknown): value is 'light' | 'dark' {
  return value === 'light' || value === 'dark';
}

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isExplicit(stored) ? stored : 'system';
  } catch {
    // Storage can be blocked (private mode, site data off): follow the device.
    return 'system';
  }
}

/** Points every <meta name="theme-color"> at the chosen theme, or back at its own media query. */
function syncThemeColor(preference: ThemePreference): void {
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const ownTheme = meta.media.includes('dark') ? 'dark' : 'light';
    meta.content = THEME_BACKGROUND[preference === 'system' ? ownTheme : preference];
  }
}

export function applyThemePreference(preference: ThemePreference): void {
  const root = document.documentElement;
  if (isExplicit(preference)) {
    root.dataset.theme = preference;
  } else {
    delete root.dataset.theme;
  }
  syncThemeColor(preference);
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    if (isExplicit(preference)) {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } else {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    }
  } catch {
    // Not stored, but still applied for this visit.
  }
  applyThemePreference(preference);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Calls `onChange` after a change made here or in another tab; returns the unsubscribe function. */
export function subscribeThemePreference(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) {
      applyThemePreference(readThemePreference());
      onChange();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}
