import { AutoThemeIcon, MoonIcon, SunIcon } from '@/components/icons';
import type { ThemePreference } from '@/theme/theme';

/** One icon per theme choice, shared by the switcher in the profile page and the toggle in the top bar. */
export const THEME_ICONS: Record<ThemePreference, typeof SunIcon> = {
  system: AutoThemeIcon,
  light: SunIcon,
  dark: MoonIcon,
};
