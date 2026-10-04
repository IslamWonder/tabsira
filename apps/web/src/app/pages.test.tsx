import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Metadata } from 'next';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import AtlasPage, { metadata as atlasMetadata } from './atlas/page';
import CommunityPage, { metadata as communityMetadata } from './community/page';
import ErrorPage from './error';
import manifest from './manifest';
import MePage, { metadata as meMetadata } from './me/page';
import NotFound, { metadata as notFoundMetadata } from './not-found';
import OfflinePage, { metadata as offlineMetadata } from './offline/page';
import ScenePage, { metadata as sceneMetadata } from './page';
import WorldPage, { metadata as worldMetadata } from './world/page';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

describe('placeholder routes', () => {
  it.each<[string, () => ReactElement, Metadata, string, string]>([
    ['/world', WorldPage, worldMetadata, 'عالمي', '/world'],
    ['/community', CommunityPage, communityMetadata, 'تبصرة تواصل', '/community'],
    ['/atlas', AtlasPage, atlasMetadata, 'أطلس بصائر العالم', '/atlas'],
    ['/me', MePage, meMetadata, 'ملفي', '/me'],
  ])(
    '%s says «قريبًا» honestly and has its canonical address',
    (_route, Page, metadata, title, canonical) => {
      render(<Page />);
      expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
      expect(screen.getByText('قريبًا')).toBeInTheDocument();
      expect(metadata.alternates?.canonical).toBe(canonical);
    }
  );

  it('keeps the personal spaces out of search engines', () => {
    expect(worldMetadata.robots).toEqual({ index: false, follow: false });
    expect(meMetadata.robots).toEqual({ index: false, follow: false });
  });

  it('lets «ملفي» choose the theme and the decorative motion already', () => {
    render(<MePage />);
    expect(screen.getByRole('group', { name: 'المظهر' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'الحركة الزخرفية' })).toBeInTheDocument();
    const sections = screen.getByRole('navigation', { name: 'أقسام ملفي' });
    expect(sections.querySelectorAll('a')).toHaveLength(3);
  });

  it('opens on the scene', () => {
    render(<ScenePage />);
    expect(
      screen.getByRole('img', { name: 'نبتة زيتون صغيرة تتلقى قطرات المطر' })
    ).toBeInTheDocument();
    expect(sceneMetadata.alternates?.canonical).toBe('/');
  });
});

describe('error, not found and offline', () => {
  it('not found leads back to the start', () => {
    render(<NotFound />);
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
