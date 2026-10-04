import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ThemeToggle } from './theme-toggle';

describe('ThemeToggle', () => {
  it('names the current choice and cycles automatic, light, dark', async () => {
    render(<ThemeToggle />);
    const button = screen.getByRole('button', { name: 'المظهر: تلقائي' });
    expect(button).toHaveAttribute('title', 'المظهر: تلقائي');
    await userEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe('light');
    await userEvent.click(screen.getByRole('button', { name: 'المظهر: فاتح' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'المظهر: داكن' }));
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(screen.getByRole('button', { name: 'المظهر: تلقائي' })).toBeInTheDocument();
  });
});
