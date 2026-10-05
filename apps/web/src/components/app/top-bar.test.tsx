import { render as renderBare, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import { mockApi } from '@/test/api';
import { forgetDevice, stubCamera } from '@/test/camera';
import { USER } from '@/test/fixtures';
import { THEME_STORAGE_KEY } from '@/theme/theme';
import { TopBar } from './top-bar';

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

describe('TopBar', () => {
  it('appears from tablet up only', () => {
    render(<TopBar />);
    expect(screen.getByRole('banner', { hidden: true })).toHaveClass('hidden', 'tablet:block');
  });

  it('puts the brand first, the four sections as tabs, and one primary action last', () => {
    render(<TopBar />);
    const links = screen.getAllByRole('link');
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[0]).toHaveAccessibleName('تبصرة');
    expect(within(links[0] as HTMLElement).getByRole('img', { name: 'تبصرة' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'التنقل الرئيسي' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent)
    ).toEqual(['عالمي', 'تواصل', 'الأطلس', 'ملفي']);
    const capture = screen.getByRole('button', { name: 'صوّر مشهدًا' });
    expect(capture.className).toContain('fill-cta');
    expect(capture).toHaveAttribute('aria-haspopup', 'dialog');
    expect(screen.getByRole('link', { name: 'دخول' })).toHaveAttribute('href', '/signin');
  });

  it('offers signing in as a secondary button, with no second sign-up button', () => {
    render(<TopBar />);
    const signIn = screen.getByRole('link', { name: 'دخول' });
    expect(signIn.className).toContain('border-[1.5px]');
    expect(signIn.className).not.toContain('fill-');
    expect(screen.queryByRole('link', { name: 'أنشئ حسابًا' })).toBeNull();
  });

  it('drops the sign-in link once the API says someone is signed in', async () => {
    mockApi({ 'GET /auth/me': { body: USER } });
    pathname.value = '/signin';
    render(<TopBar />);
    expect(screen.getByRole('link', { name: 'دخول' })).toHaveAttribute('aria-current', 'page');
    await waitFor(() => expect(screen.queryByRole('link', { name: 'دخول' })).toBeNull());
  });

  it('marks a tab current on its section', () => {
    pathname.value = '/atlas';
    render(<TopBar />);
    expect(screen.getByRole('link', { current: 'page' })).toHaveTextContent('الأطلس');
  });

  it('opens the live camera from any page with «صوّر مشهدًا»', async () => {
    const { getUserMedia } = stubCamera('granted');
    pathname.value = '/atlas';
    render(<TopBar />);

    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));

    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    expect(await within(sheet).findByLabelText('معاينة الكاميرا')).toBeInTheDocument();
    // The file picker stays beside the camera.
    expect(within(sheet).getByLabelText('اختر صورة')).toBeInTheDocument();
  });

  it('carries the theme toggle', async () => {
    render(<TopBar />);
    await userEvent.click(screen.getByRole('button', { name: 'المظهر: تلقائي' }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });
});
