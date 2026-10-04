import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { clip, DESCRIPTION_MAX, TITLE_MAX } from '@/lib/public-insight';
import { apiError, mockApi } from '@/test/api';
import { HADITH_TEXT, publicInsightOut, sha256, VERSE_TEXT } from '@/test/scan';
import PublicInsightPage, { generateMetadata } from './[id]/page';

class NotFoundSignal extends Error {}

vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new NotFoundSignal('not found');
  },
}));

const ID = '110000000000000002';
const params = (id: string) => ({ params: Promise.resolve({ id }) });
const route = `GET /public/insights/${ID}`;

/** The texts of the JSON-LD scripts on the page, parsed. */
function structuredData(container: HTMLElement): Record<string, unknown>[] {
  return Array.from(container.querySelectorAll('script[type="application/ld+json"]')).map(
    (script) => JSON.parse(script.textContent ?? '{}') as Record<string, unknown>
  );
}

describe('the public page of a published insight', () => {
  it("prints the verse and the hadith exactly as the API returns them, and the owner's public name only", async () => {
    mockApi({ [route]: { body: publicInsightOut() } });
    const { container } = render(await PublicInsightPage(params(ID)));

    expect(
      screen.getByRole('heading', { level: 1, name: 'عنوان البصيرة الأولى' })
    ).toBeInTheDocument();
    const verse = container.querySelector('[data-scripture="quran"]');
    expect(verse?.textContent).toBe(VERSE_TEXT);
    expect(sha256(verse?.textContent ?? '')).toBe(publicInsightOut().quran?.verse.sha256);
    const hadith = container.querySelector('[data-scripture="hadith"]');
    expect(hadith?.textContent).toBe(HADITH_TEXT);
    expect(sha256(hadith?.textContent ?? '')).toBe(publicInsightOut().hadith?.hadith.sha256);
    expect(screen.getByText('نشرها قارئ')).toBeInTheDocument();
    expect(screen.getByText('ما ظهر في الصورة:').parentElement?.textContent).toContain(
      'نبتة صغيرة وماء.'
    );
    expect(screen.getByText('احفظ الدعاء الوارد في الحديث.')).toBeInTheDocument();
    expect(screen.getByText('الإحياء بالماء')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'جرّب تبصرة بمشهدك' })).toHaveAttribute('href', '/');
    expect(screen.getByText(/تبصرة أداة مدعومة/)).toBeInTheDocument();
    // Nothing of the owner's own page: no chat, no step buttons, no photo.
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).not.toContain('ناقش');

    const data = structuredData(container);
    expect(data.map((item) => item['@type'])).toEqual(['WebPage', 'BreadcrumbList', 'Article']);
    const article = data[2] as { author: { name: string }; headline: string; url: string };
    expect(article.author.name).toBe('قارئ');
    expect(article.headline).toBe('عنوان البصيرة الأولى');
    expect(article.url).toMatch(new RegExp(`/i/${ID}$`));
    // Structured data never carries scripture (docs/SEO.md §3).
    expect(JSON.stringify(data)).not.toContain('آية للاختبار');
    expect(JSON.stringify(data)).not.toContain('حديث للاختبار');
  });

  it('builds indexable article metadata from the title and the glimpse alone', async () => {
    mockApi({ [route]: { body: publicInsightOut() } });
    const metadata = await generateMetadata(params(ID));

    expect(metadata.title).toBe('عنوان البصيرة الأولى');
    expect(metadata.description).toBe('بصيرة من تبصرة: لمحة البصيرة الأولى');
    expect(metadata.alternates?.canonical).toBe(`/i/${ID}`);
    expect(metadata.robots).toEqual({ index: true, follow: true });
    expect(metadata.openGraph).toMatchObject({ type: 'article', url: `/i/${ID}` });
    expect(JSON.stringify(metadata)).not.toContain('قارئ');
  });

  it('names the organisation as the author when the owner chose no public name, and shows a prepared label', async () => {
    mockApi({
      [route]: {
        body: publicInsightOut({
          author: null,
          label: 'مثال موثّق مُعدّ',
          small_step: null,
          why: { visible_clues: [], concept: 'المعنى', limits: [] },
          explanation: [{ section: 'value', label: 'القيمة', text: 'الماء نعمة.' }],
        }),
      },
    });
    const { container } = render(await PublicInsightPage(params(ID)));

    expect(screen.queryByText(/نشرها/)).toBeNull();
    expect(screen.queryByText('ما ظهر في الصورة:')).toBeNull();
    expect(screen.getByText('مثال موثّق مُعدّ')).toBeInTheDocument();
    expect(screen.queryByText('الخطوة الصغيرة')).toBeNull();
    const article = structuredData(container)[2] as { author: Record<string, string> };
    expect(article.author).toEqual({ '@id': expect.stringMatching(/#organization$/) });
  });

  it('answers not found for a bad id without asking the API, and for an insight the API does not publish', async () => {
    const api = mockApi({ [route]: apiError(404, 'NOT_FOUND') });
    await expect(PublicInsightPage(params('abc'))).rejects.toBeInstanceOf(NotFoundSignal);
    expect(api.requests).toHaveLength(0);
    await expect(generateMetadata(params(ID))).rejects.toBeInstanceOf(NotFoundSignal);
    expect(api.requests).toHaveLength(1);
  });

  it('treats an id the API refuses as not found too, and keeps a long title within the limits', async () => {
    const huge = '9999999999999999999';
    mockApi({
      [`GET /public/insights/${huge}`]: apiError(422, 'VALIDATION_ERROR'),
      [route]: { body: publicInsightOut({ title: 'كلمة '.repeat(30).trim() }) },
    });
    await expect(PublicInsightPage(params(huge))).rejects.toBeInstanceOf(NotFoundSignal);
    const metadata = await generateMetadata(params(ID));
    expect(String(metadata.title).length).toBeLessThanOrEqual(TITLE_MAX);
    expect(String(metadata.title).endsWith('…')).toBe(true);
  });

  it('fails loudly, not silently, when the API is down', async () => {
    mockApi({ [route]: 'network-error' });
    await expect(PublicInsightPage(params(ID))).rejects.toThrow(/public insight/);
  });
});

describe('clip', () => {
  it('keeps a short text, cuts a long one at a word and marks the cut', () => {
    expect(clip('  قصير  ', TITLE_MAX)).toBe('قصير');
    const long = Array.from({ length: 40 }, (_, i) => `كلمة${i}`).join(' ');
    const cut = clip(long, DESCRIPTION_MAX);
    expect(cut.length).toBeLessThanOrEqual(DESCRIPTION_MAX);
    expect(cut.endsWith('…')).toBe(true);
    expect(cut).not.toMatch(/ …$/);
    // A single word longer than the limit is cut inside the word.
    expect(clip('ا'.repeat(100), 10)).toBe(`${'ا'.repeat(9)}…`);
  });
});
