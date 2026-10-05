import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { apiError, mockApi } from '@/test/api';
import { HADITH_TEXT, publicInsightOut, sha256, VERSE_TEXT } from '@/test/scan';
import PublicInsightRoute, { generateMetadata } from './page';

class NotFoundSignal extends Error {}

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  notFound: () => {
    throw new NotFoundSignal('not found');
  },
}));

const ID = '110000000000000002';
const API_PATH = `/public/insights/${ID}`;
const params = (id: string) => ({ params: Promise.resolve({ id }) });

async function open(overrides = {}) {
  mockApi({ [`GET ${API_PATH}`]: { body: publicInsightOut(overrides) } });
  const { container } = render(await PublicInsightRoute(params(ID)));
  return container;
}

describe('the public page of an insight', () => {
  it('shows the verse and the hadith byte for byte, with their stored hashes', async () => {
    const container = await open();
    const verse = container.querySelector('[data-scripture="quran"]');
    const hadith = container.querySelector('[data-scripture="hadith"]');
    expect(verse?.textContent).toBe(VERSE_TEXT);
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    const shown = publicInsightOut();
    expect(sha256(verse?.textContent ?? '')).toBe(shown.quran?.verse.sha256);
    expect(sha256(hadith?.textContent ?? '')).toBe(shown.hadith?.hadith.sha256);
  });

  it('reads the public route without a cookie and asks for nothing else', async () => {
    const api = mockApi({ [`GET ${API_PATH}`]: { body: publicInsightOut() } });
    render(await PublicInsightRoute(params(ID)));
    // Besides the session every page reads (the top bar's, shared), nothing but the public route.
    await waitFor(() => expect(api.requests.length).toBe(2));
    expect(api.requests.map((request) => new URL(request.url).pathname)).toEqual([
      API_PATH,
      '/auth/me',
    ]);
  });

  it('gives the title, the author as given, the disclosure and the way into the app', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('عنوان البصيرة الأولى');
    expect(screen.getByText('سارة')).toBeInTheDocument();
    expect(screen.getByText('@sara_21')).toBeInTheDocument();
    expect(screen.getByText(publicInsightOut().disclosure)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'صوّر مشهدًا' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'ادخل إلى حسابك' })).toHaveAttribute('href', '/signin');
  });

  it('shows the handle alone when the owner agreed to no public name', async () => {
    await open({ author: { handle: 'sara_21', public_name: null } });
    expect(screen.getByText('@sara_21')).toBeInTheDocument();
    expect(screen.queryByText('سارة')).not.toBeInTheDocument();
  });

  it('names no author when the owner chose none, and shows no photo', async () => {
    const container = await open({ author: null });
    expect(screen.queryByText('@sara_21')).not.toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script[type="application/ld+json"]')).not.toBeNull();
  });

  it('prints structured data of an article and a trail, with no scripture in it', async () => {
    const container = await open();
    const blocks = [...container.querySelectorAll('script[type="application/ld+json"]')].map(
      (script) => script.textContent ?? ''
    );
    const types = blocks.map((block) => JSON.parse(block)['@type']);
    expect(types).toEqual(['Article', 'BreadcrumbList']);
    expect(JSON.parse(blocks[0] ?? '')).toMatchObject({
      headline: 'عنوان البصيرة الأولى',
      url: `https://tabsira.test/insights/${ID}`,
      author: { name: 'سارة' },
    });
    for (const block of blocks) {
      expect(block).not.toContain(VERSE_TEXT);
      expect(block).not.toContain(HADITH_TEXT);
    }
  });

  it('renders the API disclosure, not a copy of the web', async () => {
    await open({ disclosure: 'إفصاح من الخادم' });
    expect(screen.getByText('إفصاح من الخادم')).toBeInTheDocument();
  });

  it('shows the date in the owners zone, whatever the server zone', async () => {
    await open({ published_at: '2026-10-04T23:30:00Z' });
    expect(screen.getByText(/5/, { selector: 'time' })).toBeInTheDocument();
  });

  it.each([
    ['pipeline', 'مثال موثّق مُعدّ'],
    ['prepared', 'مثال موثّق مُعدّ'],
    ['demo', 'محاكاة مُعلَنة من الخادم'],
  ])('shows the API label of a %s insight', async (engine, label) => {
    await open({ engine, label });
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('shows the small step as the API labels it, and none when there is none', async () => {
    await open();
    expect(screen.getByText('من السنة')).toBeInTheDocument();
    expect(screen.getByText('احفظ الدعاء الوارد في الحديث.')).toBeInTheDocument();
    cleanup();
    await open({ small_step: null });
    expect(screen.queryByText('من السنة')).not.toBeInTheDocument();
  });

  it('shows no notice and no hadith card when no hadith was kept', async () => {
    await open({ hadith: null, hadith_status: 'none' });
    expect(screen.queryByRole('article', { name: 'السنة' })).not.toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});

describe('the metadata of the public page', () => {
  it('is indexable, article-typed and canonical on its own path, from the site origin', async () => {
    mockApi({ [`GET ${API_PATH}`]: { body: publicInsightOut() } });
    const metadata = await generateMetadata(params(ID));
    expect(metadata.alternates?.canonical).toBe(`/insights/${ID}`);
    expect(metadata.openGraph).toMatchObject({ type: 'article', url: `/insights/${ID}` });
    expect(metadata.robots).toMatchObject({ index: true });
    expect(metadata.description).toBe('لمحة البصيرة الأولى');
  });

  it('keeps an unavailable insight out of results, naming only its path', async () => {
    mockApi({ [`GET ${API_PATH}`]: apiError(503, 'service_unavailable') });
    const metadata = await generateMetadata(params(ID));
    expect(metadata.robots).toMatchObject({ index: false });
    expect(metadata.title).toBe('تعذّر عرض البصيرة الآن');
  });
});

describe('what is not shown', () => {
  it.each([
    ['unknown, unpublished or withdrawn (the API answers 404)', apiError(404, 'not_found')],
  ])('answers not found for %s, in the page and in its metadata', async (_name, reply) => {
    mockApi({ [`GET ${API_PATH}`]: reply });
    await expect(PublicInsightRoute(params(ID))).rejects.toBeInstanceOf(NotFoundSignal);
    await expect(generateMetadata(params(ID))).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it.each([400, 422])('answers not found when the API refuses the id with %i', async (status) => {
    mockApi({ [`GET ${API_PATH}`]: apiError(status, 'validation_error') });
    await expect(PublicInsightRoute(params(ID))).rejects.toBeInstanceOf(NotFoundSignal);
    await expect(generateMetadata(params(ID))).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it('answers not found for an id beyond the API range, without asking it', async () => {
    const api = mockApi({});
    await expect(PublicInsightRoute(params('9999999999999999999'))).rejects.toBeInstanceOf(
      NotFoundSignal
    );
    expect(api.requests).toHaveLength(0);
  });

  it('answers not found for what is not a public id, without asking the API', async () => {
    const api = mockApi({});
    await expect(PublicInsightRoute(params('abc'))).rejects.toBeInstanceOf(NotFoundSignal);
    expect(api.requests).toHaveLength(0);
  });

  it('shows the error page, not a false not-found, when the API does not answer', async () => {
    mockApi({ [`GET ${API_PATH}`]: 'network-error' });
    await expect(PublicInsightRoute(params(ID))).rejects.toThrow('public insight unavailable');
  });
});
