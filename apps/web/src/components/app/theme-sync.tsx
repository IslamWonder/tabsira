'use client';

import { useEffect } from 'react';
import { applyThemePreference, readThemePreference } from '@/theme/theme';

/**
 * Keeps <meta name="theme-color"> (the phone's status bar) in step with an
 * explicit theme once the page is interactive. The inline script in <head>
 * already set data-theme before the first paint.
 */
export function ThemeSync() {
  useEffect(() => {
    applyThemePreference(readThemePreference());
  }, []);
  return null;
}
