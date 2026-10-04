import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { ThemeSwitcher } from './theme-switcher';

describe('ThemeSwitcher', () => {
  it('offers three choices in a named group, automatic first', () => {
    render(<ThemeSwitcher className="extra" />);
    const group = screen.getByRole('group', { name: 'المظهر' });
    expect(group).toHaveClass('extra');
    expect(group).toHaveAccessibleDescription(/يتبع إعداد جهازك/);
    const radios = screen.getAllByRole('radio');
    expect(radios.map((radio) => radio.getAttribute('value'))).toEqual(['system', 'light', 'dark']);
    expect(screen.getByRole('radio', { name: 'تلقائي' })).toBeChecked();
  });

  it('shows the stored choice', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    render(<ThemeSwitcher />);
    expect(screen.getByRole('radio', { name: 'فاتح' })).toBeChecked();
  });

  it('applies and stores a new choice, and goes back to the device', async () => {
    render(<ThemeSwitcher />);
    await userEvent.click(screen.getByRole('radio', { name: 'داكن' }));
    expect(screen.getByRole('radio', { name: 'داكن' })).toBeChecked();
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await userEvent.click(screen.getByRole('radio', { name: 'تلقائي' }));
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('moves between choices with the arrow keys', async () => {
    render(<ThemeSwitcher />);
    await userEvent.click(screen.getByRole('radio', { name: 'تلقائي' }));
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('radio', { name: 'فاتح' })).toBeChecked();
  });
});
