// @vitest-environment node
import sharp from 'sharp';
import { describe, expect, it, vi } from 'vitest';
import { HADITH_TEXT, sha256, VERSE_TEXT } from '@/test/scan';
import { cardFaces } from './fonts';
import { drawText, escapeMarkup, markup, type TextSpec, unescapeMarkup } from './text-image';

vi.mock('sharp', async (importOriginal) => {
  const actual = await importOriginal<typeof import('sharp')>();
  return { default: vi.fn(actual.default) };
});

async function spec(overrides: Partial<TextSpec> = {}): Promise<TextSpec> {
  const faces = cardFaces();
  return {
    text: HADITH_TEXT,
    face: faces.quran,
    size: 30,
    leading: 0.3,
    width: 600,
    align: 'start',
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

  it('sets an Arabic paragraph flush right: the last line of two ends at the right edge', async () => {
    // Neutral filler words. The width is derived from the one-line width of the same words, so the
    // paragraph wraps whatever face the engine really uses: on macOS the prebuilt engine draws with
    // the system's CoreText and ignores the font file, so glyph widths differ from Linux.
    const words = Array(9).fill('كلمة').join(' ');
    const face = cardFaces().text[0] as TextSpec['face'];
    const one = await drawText(await spec({ text: 'كلمة', face, width: 2000 }));
    const whole = await drawText(await spec({ text: words, face, width: 5000 }));
    const width = Math.ceil(whole.width * 0.6);
    const drawn = await drawText(await spec({ text: words, face, width }));
    expect(drawn.height).toBeGreaterThan(one.height * 1.5);
    const { data, info } = await sharp(drawn.png).raw().toBuffer({ resolveWithObject: true });
    // The ink of the last line reaches the right edge and leaves the left side empty.
    let right = 0;
    let left = info.width;
    for (let y = Math.floor(info.height * 0.7); y < info.height; y++) {
      for (let x = 0; x < info.width; x++) {
        if ((data[(y * info.width + x) * info.channels + 3] ?? 0) > 0) {
          right = Math.max(right, x);
          left = Math.min(left, x);
        }
      }
    }
    expect(left).toBeGreaterThan(info.width * 0.1);
    expect(right).toBeGreaterThan(info.width - 12);
  });

  it('hands the engine the stored text escaped and nothing else, and it unescapes to the same bytes', async () => {
    const stored = `${HADITH_TEXT} & <x>`;
    vi.mocked(sharp).mockClear();
    await drawText(await spec({ text: stored, colour: '#fff' }));
    const call = vi
      .mocked(sharp)
      .mock.calls.map(([input]) => input as { text?: { text: string } })
      .find((input) => input.text !== undefined);
    const sent = call?.text?.text ?? '';
    expect(sent).toBe(`<span foreground="#fff" weight="400">${escapeMarkup(stored)}</span>`);
    const inner = sent.slice(sent.indexOf('>') + 1, sent.lastIndexOf('</span>'));
    expect(unescapeMarkup(inner)).toBe(stored);
    expect(sha256(unescapeMarkup(inner))).toBe(sha256(stored));
  });

  it('refuses a text with nothing to draw, so a blank card is never made', async () => {
    await expect(drawText(await spec({ text: '' }))).rejects.toThrow();
  });
});
