import { describe, expect, it } from 'vitest';
import { publicInsightOut } from '@/test/scan';
import {
  cardFileName,
  describe as describeGlimpse,
  publicInsightCardPath,
  publicInsightPath,
  publicInsightSeo,
} from './public-insight';

describe('the public insight address', () => {
  it('is /insights/{id}, the path the API gives', () => {
    expect(publicInsightPath('42')).toBe('/insights/42');
  });

  it('places the card under the page, and names its file after the id', () => {
    expect(publicInsightCardPath('42')).toBe('/insights/42/card');
    expect(cardFileName('42')).toBe('tabsira-42.png');
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
    });
  });
});
