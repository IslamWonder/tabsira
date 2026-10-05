import { render as renderBare, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { forgetDevice, stubCamera } from '@/test/camera';
import { AppNav } from './app-nav';
import { isActive } from './nav-items';

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({
  usePathname: () => pathname.value,
  useRouter: () => ({ push: vi.fn() }),
}));

// The bar lives inside the layout's CaptureProvider; so does every test of it.
const render = (ui: ReactElement) => renderBare(ui, { wrapper: CaptureProvider });

beforeEach(() => {
  pathname.value = '/';
});

afterEach(() => {
  forgetDevice();
  vi.restoreAllMocks();
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
  it('has four links in reading order with the capture button in the middle', () => {
    render(<AppNav />);
    const nav = screen.getByRole('navigation', { name: 'التنقل الرئيسي' });
    const items = within(nav).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'عالمي',
      'تواصل',
      'التقط',
      'الأطلس',
      'ملفي',
    ]);
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.getAttribute('href'))
    ).toEqual(['/world', '/community', '/atlas', '/me']);
    expect(within(items[2] as HTMLElement).getByRole('button', { name: 'التقط' })).toHaveAttribute(
      'aria-haspopup',
      'dialog'
    );
  });

  it('opens the live camera under the thumb, wherever the reader is', async () => {
    const { getUserMedia } = stubCamera('granted');
    pathname.value = '/world';
    render(<AppNav />);

    await userEvent.click(screen.getByRole('button', { name: 'التقط' }));

    expect(await screen.findByRole('dialog', { name: 'صوّر مشهدًا' })).toBeInTheDocument();
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
  });

  it('marks a side tab as current on its own pages', () => {
    pathname.value = '/me/settings';
    render(<AppNav />);
    expect(screen.getByRole('link', { current: 'page' })).toHaveAccessibleName('ملفي');
  });

  it('is for phones only: the top bar takes over from tablet up', () => {
    render(<AppNav />);
    expect(screen.getByRole('navigation')).toHaveClass('tablet:hidden');
  });

  it('keeps every target at least 48 px', () => {
    render(<AppNav />);
    for (const target of [...screen.getAllByRole('link'), screen.getByRole('button')]) {
      expect(target.className).toMatch(/\b(h-14|size-16)\b/);
    }
  });
});
