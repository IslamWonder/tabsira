import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { TopBar } from './top-bar';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

beforeEach(() => {
  pathname.value = '/';
});

describe('TopBar', () => {
  it('appears from tablet up only', () => {
    render(<TopBar />);
    expect(screen.getByRole('banner', { hidden: true })).toHaveClass('hidden', 'tablet:block');
  });

  it('puts the brand first, the four sections as tabs, and one primary action last', () => {
    render(<TopBar />);
    const links = screen.getAllByRole('link');
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[0]).toHaveTextContent('تَبْصِرَة');
    const nav = screen.getByRole('navigation', { name: 'التنقل الرئيسي' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent)
    ).toEqual(['عالمي', 'تواصل', 'الأطلس', 'ملفي']);
    const capture = links.at(-1) as HTMLElement;
    expect(capture).toHaveTextContent('صوّر مشهدًا');
    expect(capture.className).toContain('fill-cta');
    expect(screen.getByRole('link', { name: 'دخول' })).toHaveAttribute('href', '/me');
  });

  it('marks the capture action current on the scene, and a tab on its section', () => {
    const { rerender } = render(<TopBar />);
    expect(screen.getByRole('link', { name: 'صوّر مشهدًا' })).toHaveAttribute('aria-current', 'page');
    pathname.value = '/atlas';
    rerender(<TopBar />);
    expect(screen.getByRole('link', { name: 'صوّر مشهدًا' })).not.toHaveAttribute('aria-current');
    const current = screen.getByRole('link', { current: 'page' });
    expect(current).toHaveTextContent('الأطلس');
  });

  it('carries the theme toggle', async () => {
    render(<TopBar />);
    await userEvent.click(screen.getByRole('button', { name: 'المظهر: تلقائي' }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });
});
