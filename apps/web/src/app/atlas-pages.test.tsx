import { cleanup, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { ENTRY, ORPHAN_ENTRY, PLACE_PAGE, SPONSORED_ENTRY } from '@/test/atlas';
import AtlasCameraPage, { metadata as cameraMetadata } from './atlas/camera/page';
import AtlasEntryPage, { generateMetadata as entryMetadata } from './atlas/entries/[id]/page';
import AtlasPage from './atlas/page';
import AtlasPlacePage, { generateMetadata as placeMetadata } from './atlas/places/[id]/page';
import AtlasPublishPage from './atlas/publish/page';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => ({ get: () => null }),
  notFound: () => {
    throw new Error('NEXT_NOT_FOUND');
  },
}));

const params = <T extends Record<string, string>>(value: T) => ({ params: Promise.resolve(value) });
const NOINDEX = { index: false, follow: false };

describe('the atlas entry page metadata', () => {
  it('describes a published entry by its title and glimpse, as an article, with no cookie sent', async () => {
    const api = mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY } });
    const metadata = await entryMetadata(params({ id: ENTRY.id }));
    expect(metadata.title).toBe('[عنوان البصيرة]');
    expect(metadata.description).toBe('[لمحة البصيرة]');
    expect(metadata.robots).toMatchObject({ index: true });
    expect(metadata.openGraph).toMatchObject({ type: 'article' });
    expect(metadata.openGraph?.images).toEqual([
      {
        url: `/atlas/entries/${ENTRY.id}/preview`,
        width: 1200,
        height: 630,
        alt: '[عنوان البصيرة]',
      },
    ]);
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
    // The public point is not in the metadata either; only words are.
    expect(JSON.stringify(metadata)).not.toContain('36.80');
  });

  it('keeps an entry whose place was widened out of results, with its words', async () => {
    const widened = {
      ...ENTRY,
      author: null,
      location: { ...ENTRY.location, widened_level: 'region' as const },
    };
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: { body: widened } });
    const metadata = await entryMetadata(params({ id: ENTRY.id }));
    expect(metadata.robots).toEqual(NOINDEX);
    expect(metadata.title).toBe('[عنوان البصيرة]');
  });

  it('keeps a gone, missing, unreachable or malformed entry out of results', async () => {
    for (const route of [
      apiError(410, 'GONE'),
      apiError(404, 'NOT_FOUND'),
      'network-error' as const,
    ]) {
      mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: route });
      const metadata = await entryMetadata(params({ id: ENTRY.id }));
      expect(metadata.robots).toEqual(NOINDEX);
      expect(metadata.title).toBe('أطلس بصائر العالم');
    }
    const api = mockApi({});
    expect((await entryMetadata(params({ id: 'x' }))).robots).toEqual(NOINDEX);
    expect(api.requests).toHaveLength(0);
  });

  it('renders the article data and the screen', async () => {
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: { body: ENTRY } });
    const { container } = render(await AtlasEntryPage(params({ id: ENTRY.id })));
    expect(container.querySelector('script[type="application/ld+json"]')?.textContent).toContain(
      '"[اسم عام]"'
    );
    expect(screen.getByText('نحمّل البصائر…')).toBeInTheDocument();
  });

  it('names no author in the article data of an entry whose place was widened', async () => {
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: { body: { ...ENTRY, author: null } } });
    const { container } = render(await AtlasEntryPage(params({ id: ENTRY.id })));
    const data = container.querySelector('script[type="application/ld+json"]')?.textContent;
    expect(data).toContain('"headline"');
    expect(data).not.toContain('"author"');
  });
});

describe('the atlas entry page for an author who shows no full name', () => {
  it('names no author in the article data, the handle never standing for a name', async () => {
    mockApi({
      [`GET /atlas/entries/${ENTRY.id}`]: {
        body: { ...ENTRY, author: { handle: 'rain_reader', public_name: null } },
      },
    });
    const { container } = render(await AtlasEntryPage(params({ id: ENTRY.id })));
    const data = container.querySelector('script[type="application/ld+json"]')?.textContent;
    expect(data).toContain('"headline"');
    expect(data).not.toContain('"author"');
    expect(data).not.toContain('rain_reader');
  });
});

describe('the atlas entry page for an entry that cannot be shown', () => {
  it('renders the screen without article data for a gone entry or a malformed id', async () => {
    mockApi({ [`GET /atlas/entries/${ENTRY.id}`]: apiError(410, 'GONE') });
    const gone = render(await AtlasEntryPage(params({ id: ENTRY.id })));
    expect(gone.container.querySelector('script[type="application/ld+json"]')).toBeNull();
    cleanup();
    mockApi({});
    const malformed = render(await AtlasEntryPage(params({ id: 'x' })));
    expect(malformed.container.querySelector('script[type="application/ld+json"]')).toBeNull();
  });
});

describe('the atlas place page metadata', () => {
  it('names the place while it has an entry, and hides it otherwise', async () => {
    mockApi({ 'GET /atlas/places/2464470': { body: PLACE_PAGE } });
    const metadata = await placeMetadata(params({ id: '2464470' }));
    expect(metadata.title).toBe('ذاكرة المكان: [تونس]');
    expect(metadata.description).toBe('البصائر التي نشرها الناس في [تونس] على أطلس تبصرة.');
    expect(metadata.robots).toMatchObject({ index: true });

    mockApi({ 'GET /atlas/places/999': apiError(404, 'NOT_FOUND') });
    expect((await placeMetadata(params({ id: '999' }))).robots).toEqual(NOINDEX);
    const api = mockApi({});
    expect((await placeMetadata(params({ id: '0' }))).robots).toEqual(NOINDEX);
    expect(api.requests).toHaveLength(0);
  });

  it('renders the place screen for a valid id', async () => {
    mockApi({});
    render(await AtlasPlacePage(params({ id: '2464470' })));
    expect(screen.getByText('نحمّل المكان…')).toBeInTheDocument();
  });

  it('still renders the place screen for a malformed id, which it never looks up', async () => {
    mockApi({});
    render(await AtlasPlacePage(params({ id: 'x' })));
    expect(screen.getByText('نحمّل المكان…')).toBeInTheDocument();
  });
});

describe('the camera discovery page (the camera_discovery feature)', () => {
  it('is a 404 while the flag is off, on the atlas too', () => {
    vi.stubEnv('DISABLED_FEATURES', 'camera_discovery');
    expect(() => render(<AtlasCameraPage />)).toThrow('NEXT_NOT_FOUND');
    mockApi({});
    render(<AtlasPage />);
    expect(screen.queryByRole('link', { name: 'اكتشف بالكاميرا' })).toBeNull();
  });

  it('opens on its explanation while the flag is on, outside the sitemap', () => {
    vi.stubEnv('DISABLED_FEATURES', '');
    mockApi({});
    render(<AtlasCameraPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'اكتشف البصائر حولك' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ابدأ الاستكشاف' })).toBeInTheDocument();
    expect(cameraMetadata.alternates?.canonical).toBe('/atlas/camera');
    expect(cameraMetadata.robots).toEqual({ index: false, follow: false });
    cleanup();
    render(<AtlasPage />);
    expect(screen.getByRole('link', { name: 'اكتشف بالكاميرا' })).toHaveAttribute(
      'href',
      '/atlas/camera'
    );
  });
});

describe('the atlas pages (the atlas feature)', () => {
  it('do not exist while the flag is off: the map and the placing screen are 404s (decision 1)', () => {
    vi.stubEnv('DISABLED_FEATURES', 'atlas');
    mockApi({});
    expect(() => render(<AtlasPage />)).toThrow('NEXT_NOT_FOUND');
    expect(() => render(<AtlasPublishPage />)).toThrow('NEXT_NOT_FOUND');
  });

  it('open while the flag is on', () => {
    vi.stubEnv('DISABLED_FEATURES', '');
    mockApi({});
    render(<AtlasPage />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'أطلس بصائر العالم' })
    ).toBeInTheDocument();
    cleanup();
    render(<AtlasPublishPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'اختر بصيرة أولًا' })).toBeInTheDocument();
  });
});

describe('the sponsoring switch (atlas_sponsorship)', () => {
  const routes = (entry: typeof ORPHAN_ENTRY) => ({
    'GET /auth/me': apiError(401, 'UNAUTHORIZED'),
    [`GET /atlas/entries/${entry.id}`]: { body: entry },
  });
  const section = { name: 'كفالة البصيرة' };

  it('hides the sponsoring part of an entry while it is off, and shows it while it is on', async () => {
    vi.stubEnv('DISABLED_FEATURES', 'atlas_sponsorship');
    mockApi(routes(ORPHAN_ENTRY));
    render(await AtlasEntryPage(params({ id: ORPHAN_ENTRY.id })));
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('region', section)).toBeNull();
    cleanup();

    vi.stubEnv('DISABLED_FEATURES', '');
    mockApi(routes(ORPHAN_ENTRY));
    render(await AtlasEntryPage(params({ id: ORPHAN_ENTRY.id })));
    expect(await screen.findByRole('region', section)).toBeInTheDocument();
  });

  it('links the sponsor to their profile only while the social network is on', async () => {
    vi.stubEnv('DISABLED_FEATURES', '');
    mockApi(routes(SPONSORED_ENTRY));
    render(await AtlasEntryPage(params({ id: SPONSORED_ENTRY.id })));
    expect(await screen.findByRole('link', { name: /\[اسم الكافل\]/ })).toBeInTheDocument();
    cleanup();

    vi.stubEnv('DISABLED_FEATURES', 'social');
    mockApi(routes(SPONSORED_ENTRY));
    render(await AtlasEntryPage(params({ id: SPONSORED_ENTRY.id })));
    expect(await screen.findByText(/@quiet_keeper/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /\[اسم الكافل\]/ })).toBeNull();
  });
});
