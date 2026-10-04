// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { HADITH_TEXT, sha256, VERSE_TEXT } from '@/test/scan';
import { cardFaces } from './fonts';
import { drawText, escapeMarkup, markup, type TextSpec, unescapeMarkup } from './text-image';

async function spec(overrides: Partial<TextSpec> = {}): Promise<TextSpec> {
  const faces = await cardFaces();
  return {
    text: HADITH_TEXT,
    face: faces.quran,
    size: 30,
    leading: 0.3,
    width: 600,
    align: 'right',
    colour: '#EEF3EF',
    ...overrides,
  };
}

describe('text as markup', () => {
  it('writes the three markup characters as entities and nothing else', () => {
    expect(escapeMarkup('a & b < c > d')).toBe('a &amp; b &lt; c &gt; d');
    expect(escapeMarkup(VERSE_TEXT)).toBe(VERSE_TEXT);
  });

  it('gives back the stored text, byte for byte, after the trip', () => {
    for (const text of [VERSE_TEXT, HADITH_TEXT, 'a & <b> &amp; c']) {
      const back = unescapeMarkup(markup({ text } as TextSpec));
      expect(back).toContain(text);
      expect(sha256(unescapeMarkup(escapeMarkup(text)))).toBe(sha256(text));
    }
  });

  it('names the colour and the weight', () => {
    expect(markup({ text: 'x', colour: '#fff' } as TextSpec)).toBe(
      '<span foreground="#fff" weight="400">x</span>'
    );
    expect(markup({ text: 'x', colour: '#fff', weight: 600 } as TextSpec)).toContain(
      'weight="600"'
    );
  });
});

describe('drawing text', () => {
  it('draws a transparent PNG as wide as its longest line and as high as its lines need', async () => {
    const one = await drawText(await spec({ text: 'a' }));
    const many = await drawText(await spec({ text: `${VERSE_TEXT} `.repeat(20) }));
    expect(one.png.subarray(1, 4).toString()).toBe('PNG');
    expect(one.width).toBeGreaterThan(0);
    expect(many.width).toBeLessThanOrEqual(600);
    expect(many.height).toBeGreaterThan(one.height * 2);
  });

  it('refuses a text with nothing to draw, so a blank card is never made', async () => {
    await expect(drawText(await spec({ text: '' }))).rejects.toThrow();
  });
});
