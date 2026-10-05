import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Metadata } from 'next';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CaptureProvider } from '@/components/capture/capture-provider';
import AtlasPage, { metadata as atlasMetadata } from './atlas/page';
import CommunityPage, { metadata as communityMetadata } from './community/page';
import CommunityPublishPage from './community/publish/page';
import ErrorPage from './error';
import manifest from './manifest';
import MePage, { metadata as meMetadata } from './me/page';
import PracticePage, { metadata as practiceMetadata } from './me/practice/page';
import NotFound, { metadata as notFoundMetadata } from './not-found';
import OfflinePage, { metadata as offlineMetadata } from './offline/page';
import HomePage, { metadata as homeMetadata } from './page';
import WorldPage, { metadata as worldMetadata } from './world/page';

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  notFound: () => {
    throw new Error('NEXT_NOT_FOUND');
  },
}));

describe('placeholder routes', () => {
  it.each<[string, () => ReactElement, Metadata, string, string]>([])(
    '%s says «قريبًا» honestly and has its canonical address',
    (_route, Page, metadata, title, canonical) => {
      render(<Page />);
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
      expect(screen.getByText('قريبًا')).toBeInTheDocument();
      expect(metadata.alternates?.canonical).toBe(canonical);
    }
  );

  it('opens «تبصرة تواصل» on its feeds, outside the sitemap', () => {
    render(<CommunityPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'تبصرة تواصل' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'لك',
      'أتابع',
      'الأحدث',
    ]);
    expect(communityMetadata.alternates?.canonical).toBe('/community');
    expect(communityMetadata.robots).toEqual({ index: false, follow: false });
  });

  it('opens the atlas on its map and list, outside the sitemap', () => {
    render(<AtlasPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'أطلس بصائر العالم' })
    ).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'خريطة الأطلس' })).toBeInTheDocument();
    expect(atlasMetadata.alternates?.canonical).toBe('/atlas');
    expect(atlasMetadata.robots).toEqual({ index: false, follow: false });
  });

  it('keeps the personal spaces out of search engines', () => {
    expect(worldMetadata.robots).toEqual({ index: false, follow: false });
    expect(meMetadata.robots).toEqual({ index: false, follow: false });
    expect(practiceMetadata.robots).toEqual({ index: false, follow: false });
  });

  it.each<[string, () => ReactElement, Metadata, string, string]>([
    ['/world', WorldPage, worldMetadata, 'عالمي', '/world'],
    ['/me/practice', PracticePage, practiceMetadata, 'تمرينك', '/me/practice'],
    ['/me', MePage, meMetadata, 'ملفي', '/me'],
  ])(
    '%s is a real screen with its canonical address',
    (_route, Page, metadata, title, canonical) => {
      render(<Page />);
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
      expect(screen.queryByText('قريبًا')).toBeNull();
      expect(metadata.alternates?.canonical).toBe(canonical);
    }
  );

  it('lets «ملفي» choose the theme and the decorative motion already', () => {
    render(<MePage />);
    expect(screen.getByRole('group', { name: 'المظهر' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'الحركة الزخرفية' })).toBeInTheDocument();
    const sections = screen.getByRole('navigation', { name: 'أقسام ملفي' });
    // A guest (the API has not answered yet): the account, the settings, practice and cookies.
    expect(Array.from(sections.querySelectorAll('a'), (link) => link.getAttribute('href'))).toEqual(
      ['#account', '#settings', '#practice', '#app', '#cookies']
    );
  });

  it('opens on the landing page, its camera one tap away', () => {
    // The root layout's CaptureProvider holds every page; the landing page sends through it.
    render(<HomePage />, { wrapper: CaptureProvider });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('انظر إلى العالم');
    expect(screen.getAllByRole('button', { name: /صوّر مشهدًا/ }).length).toBeGreaterThan(0);
    expect(homeMetadata.alternates?.canonical).toBe('/');
  });
});

describe('error, not found and offline', () => {
  it('not found leads back to the start', () => {
    const { container } = render(<NotFound />);
    // Inline styles only: the page must read when the stylesheet fails (docs/SEO.md).
    expect(container.querySelector('[class]')).toBeNull();
    expect(container.querySelector('a')).toHaveStyle({ minHeight: '48px' });
    expect(
      screen.getByRole('heading', { level: 1, name: 'لم نجد هذه الصفحة' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'عد إلى البداية' })).toHaveAttribute('href', '/');
    expect(notFoundMetadata.robots).toEqual({ index: false, follow: false });
  });

  it('an error offers to try again and never shows the error itself', async () => {
    const retry = vi.fn();
    const error = Object.assign(new Error('secret detail'), { digest: 'abc' });
    const { container } = render(<ErrorPage error={error} retry={retry} />);
    expect(container.textContent).not.toContain('secret detail');
    expect(container.textContent).not.toContain('abc');
    await userEvent.click(screen.getByRole('button', { name: 'أعد المحاولة' }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByRole('link', { name: 'عد إلى البداية' })).toHaveAttribute('href', '/');
  });

  it('offline says what is missing and offers to try again', () => {
    render(<OfflinePage />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'أنت غير متصل الآن' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'أعد المحاولة' })).toBeInTheDocument();
    expect(offlineMetadata.robots).toEqual({ index: false, follow: false });
  });
});

describe('manifest', () => {
  it('reopens the open window and offers the camera and the world from the icon', () => {
    const app = manifest();
    expect(app.launch_handler).toEqual({ client_mode: ['navigate-existing', 'auto'] });
    expect(app.prefer_related_applications).toBe(false);
    expect(app.shortcuts?.map((shortcut) => [shortcut.name, shortcut.url])).toEqual([
      ['صوّر مشهدًا', '/?capture=1'],
      ['عالمي', '/world'],
    ]);
  });

  it('describes an installable Arabic right-to-left app named تبصرة', () => {
    const app = manifest();
    expect(app).toMatchObject({
      name: 'تبصرة',
      short_name: 'تبصرة',
      lang: 'ar',
      dir: 'rtl',
      start_url: '/',
      scope: '/',
      display: 'standalone',
      background_color: '#0B1210',
      theme_color: '#0B1210',
    });
    expect(app).not.toHaveProperty('orientation');
    expect(app.icons?.map((icon) => icon.purpose)).toEqual(['any', 'any', 'maskable']);
  });
});

describe('the network pages (FEATURE_SOCIAL)', () => {
  it('do not exist while the flag is off: the feeds and the publish screen are 404s (decision 1)', () => {
    vi.stubEnv('FEATURE_SOCIAL', 'false');
    expect(() => render(<CommunityPage />)).toThrow('NEXT_NOT_FOUND');
    expect(() => render(<CommunityPublishPage />)).toThrow('NEXT_NOT_FOUND');
  });

  it('open the publish screen while the flag is on', () => {
    vi.stubEnv('FEATURE_SOCIAL', 'true');
    render(<CommunityPublishPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'اختر بصيرة أولًا' })).toBeInTheDocument();
  });
});
