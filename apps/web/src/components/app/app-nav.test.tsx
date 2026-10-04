import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppNav } from './app-nav';
import { isActive } from './nav-items';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({ usePathname: () => pathname.value }));

beforeEach(() => {
  pathname.value = '/';
});

describe('isActive', () => {
  it('matches the home tab exactly and the others by prefix', () => {
    expect(isActive('/', '/')).toBe(true);
    expect(isActive('/', '/world')).toBe(false);
    expect(isActive('/world', '/world')).toBe(true);
    expect(isActive('/world', '/world/oasis')).toBe(true);
    expect(isActive('/world', '/worldwide')).toBe(false);
  });
});

describe('AppNav', () => {
  it('has five links in reading order with capture in the middle', () => {
    render(<AppNav />);
    const nav = screen.getByRole('navigation', { name: 'التنقل الرئيسي' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'عالمي',
      'تواصل',
      'التقط',
      'الأطلس',
      'ملفي',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/world',
      '/community',
      '/',
      '/atlas',
      '/me',
    ]);
  });

  it('marks the capture tab as the current page on the scene', () => {
    render(<AppNav />);
    const current = screen.getByRole('link', { current: 'page' });
    expect(current).toHaveAccessibleName('التقط');
    expect(current.firstElementChild).toHaveClass('ring-2');
  });

  it('marks a side tab as current on its own pages', () => {
    pathname.value = '/me/settings';
    render(<AppNav />);
    expect(screen.getByRole('link', { current: 'page' })).toHaveAccessibleName('ملفي');
    expect(screen.getByRole('link', { name: 'التقط' }).firstElementChild).not.toHaveClass('ring-2');
  });

  it('is for phones only: the top bar takes over from tablet up', () => {
    render(<AppNav />);
    expect(screen.getByRole('navigation')).toHaveClass('tablet:hidden');
  });

  it('keeps every target at least 48 px', () => {
    render(<AppNav />);
    for (const link of screen.getAllByRole('link')) {
      expect(link.className).toMatch(/\b(h-14|size-16)\b/);
    }
  });
});
