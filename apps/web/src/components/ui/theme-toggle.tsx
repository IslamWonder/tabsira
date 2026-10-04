'use client';

import { messages } from '@/messages';
import { setThemePreference, type ThemePreference } from '@/theme/theme';
import { useThemePreference } from '@/theme/use-theme-preference';
import { Button } from './button';
import { THEME_ICONS } from './theme-icons';

const NEXT: Record<ThemePreference, ThemePreference> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
};

/**
 * The top bar's one-tap theme control: automatic, then light, then dark. Its
 * name says the current choice, and hovering shows the same words as a
 * tooltip; the profile page keeps the full three-way choice.
 */
export function ThemeToggle() {
  const preference = useThemePreference();
  const Icon = THEME_ICONS[preference];
  const label = messages.theme.toggle(messages.theme[preference]);
  return (
    <Button
      variant="icon"
      label={label}
      title={label}
      onClick={() => setThemePreference(NEXT[preference])}
    >
      <Icon width="20" height="20" />
    </Button>
  );
}
