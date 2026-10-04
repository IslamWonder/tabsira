import { describe, expect, it } from 'vitest';
import { publicInsightOut } from '@/test/scan';
import { describe as describeGlimpse, publicInsightPath, publicInsightSeo } from './public-insight';

describe('the public insight address', () => {
  it('is /insights/{id}, the path the API gives', () => {
    expect(publicInsightPath('42')).toBe('/insights/42');
  });
});

describe('the description', () => {
  it('keeps a short glimpse whole', () => {
    expect(describeGlimpse('لمحة قصيرة')).toBe('لمحة قصيرة');
  });

  it('cuts a long glimpse at a word, within 165 characters', () => {
    const long = 'كلمة '.repeat(60).trim();
    const cut = describeGlimpse(long);
    expect(cut.length).toBeLessThanOrEqual(165);
    expect(cut.endsWith('…')).toBe(true);
    expect(long.startsWith(cut.slice(0, -1))).toBe(true);
  });

  it('cuts a long text with no space at the limit', () => {
    expect(describeGlimpse('ا'.repeat(300))).toHaveLength(165);
  });

  it('cuts by code points, never leaving half of an emoji', () => {
    const cut = describeGlimpse('😀'.repeat(300));
    expect(Array.from(cut)).toHaveLength(165);
    expect(cut).toBe(`${'😀'.repeat(164)}…`);
  });

  it('builds the page seo from the title and the glimpse only', () => {
    expect(publicInsightSeo(publicInsightOut({ id: '7' }))).toEqual({
      path: '/insights/7',
      title: 'عنوان البصيرة الأولى',
      description: 'لمحة البصيرة الأولى',
      type: 'article',
      image: { url: '/insights/7/card.png', width: 1200, height: 630, alt: 'عنوان البصيرة الأولى' },
    });
  });
});
