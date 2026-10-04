'use client';

import { useId } from 'react';
import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';
import { setThemePreference, THEME_PREFERENCES } from '@/theme/theme';
import { useThemePreference } from '@/theme/use-theme-preference';
import { THEME_ICONS } from './theme-icons';

export interface ThemeSwitcherProps {
  className?: string;
}

/**
 * Automatic, light or dark, stored on this device. Native radio buttons: arrow
 * keys move between the three, and screen readers announce «one of three»
 * (Jakob's law: the segmented control everyone already knows).
 */
export function ThemeSwitcher({ className }: ThemeSwitcherProps) {
  const preference = useThemePreference();
  const name = useId();
  const hintId = useId();

  return (
    <fieldset className={cx('flex flex-col gap-2', className)} aria-describedby={hintId}>
      <legend className="mb-2 font-heading font-semibold text-fg text-lg">{ar.theme.legend}</legend>
      <div className="grid grid-cols-3 gap-1 rounded-full border border-line bg-surface p-1">
        {THEME_PREFERENCES.map((option) => {
          const Icon = THEME_ICONS[option];
          const checked = option === preference;
          return (
            <label
              key={option}
              className={cx(
                'relative flex min-h-12 cursor-pointer items-center justify-center gap-2 rounded-full px-3 text-[0.9375rem]',
                'transition-[background-color,color] duration-200 has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2',
                checked ? 'fill-primary font-semibold' : 'text-fg-soft hover:text-fg'
              )}
            >
              <input
                type="radio"
                name={name}
                value={option}
                checked={checked}
                onChange={() => setThemePreference(option)}
                className="sr-only"
              />
              <Icon width="18" height="18" />
              <span>{ar.theme[option]}</span>
            </label>
          );
        })}
      </div>
      <p id={hintId} className="text-fg-muted text-sm">
        {ar.theme.hint}
      </p>
    </fieldset>
  );
}
