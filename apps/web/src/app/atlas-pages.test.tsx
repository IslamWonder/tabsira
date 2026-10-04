import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { ENTRY, PLACE_PAGE } from '@/test/atlas';
import AtlasEntryPage, { generateMetadata as entryMetadata } from './atlas/entries/[id]/page';
import AtlasPlacePage, { generateMetadata as placeMetadata } from './atlas/places/[id]/page';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

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
    expect(api.requests[0]?.headers.get('cookie')).toBeNull();
    // The public point is not in the metadata either; only words are.
    expect(JSON.stringify(metadata)).not.toContain('36.80');
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
});
