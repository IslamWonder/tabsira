'use client';

import { useSyncExternalStore } from 'react';
import { readThemePreference, subscribeThemePreference, type ThemePreference } from './theme';

function serverSnapshot(): ThemePreference {
  return 'system';
}

/**
 * The stored preference. The server cannot know it, so the first render says
 * `system` and React swaps in the stored value right after hydration.
 */
export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribeThemePreference, readThemePreference, serverSnapshot);
}
