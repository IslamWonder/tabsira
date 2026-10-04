// @vitest-environment node
import sharp from 'sharp';
import { describe, expect, it } from 'vitest';
import {
  COLOUR,
  type Parts,
  paint,
  panelHeight,
  placeFixed,
  placeGrowing,
  type Source,
} from './compose';
import { TALL, WIDE } from './layout';
import type { TextImage } from './text-image';

function image(width: number, height: number, id = 'x'): TextImage {
  // The composer reads sizes only; the id stands for the pixels so a test can find a piece.
  return { png: Buffer.from(id), width, height };
}

function source(textHeight: number, align: Source['align'] = 'right'): Source {
  return {
    tag: image(60, 28),
    reference: image(200, 28),
    text: image(900, textHeight),
    accent: COLOUR.gold,
    align,
  };
}

function parts(overrides: Partial<Parts> = {}): Parts {
  return {
    brand: image(100, 52),
    host: image(120, 24),
    label: null,
    disclosure: image(600, 24),
    author: null,
    title: image(700, 60),
    notice: null,
    pointer: null,
    verse: source(80, 'centre'),
    hadith: source(120),
    ...overrides,
  };
}

describe('placing the pieces of a card', () => {
  it('fits what was measured and places the brand at the start of a right-to-left card', () => {
    const placed = placeFixed(WIDE, parts());
    expect(placed).not.toBeNull();
    expect([placed?.width, placed?.height]).toEqual([1200, 630]);
    const brand = placed?.layers[0];
    expect(brand?.left).toBe(1200 - 44 - 100);
    expect(placed?.layers[1]?.left).toBe(44);
  });

  it('answers null when a text is wider than its column, which the composite would clip', () => {
    const wide: Source = { ...source(80), text: image(1200, 80) };
    expect(placeFixed(WIDE, parts({ verse: wide }))).toBeNull();
    expect(placeFixed(WIDE, parts({ hadith: wide }))).toBeNull();
  });

  it('answers null when a closed candidate does not hold the measured texts', () => {
    expect(placeFixed(WIDE, parts({ verse: source(900) }))).toBeNull();
  });

  it('grows a card to the height the texts need, never below its shape', () => {
    const tall = placeGrowing(TALL, parts({ verse: source(2000), hadith: null }));
    expect(tall?.height).toBeGreaterThan(1350);
    const short = placeGrowing(TALL, parts({ verse: source(100), hadith: null }));
    expect(short?.height).toBe(1350);
  });

  it('places the label in a pill beside the host, and the author at the far end of the footer', () => {
    const plain = placeFixed(WIDE, parts());
    const full = placeFixed(
      WIDE,
      parts({
        hadith: null,
        label: image(150, 24, 'label'),
        author: image(200, 24, 'author'),
        notice: image(900, 30),
        pointer: image(300, 30),
      })
    );
    const at = (id: string) => full?.layers.find((layer) => layer.input.toString() === id);
    expect(full?.layers.length).toBeGreaterThan(plain?.layers.length ?? 0);
    // The host starts the left edge; the pill and its label follow it, and the author is at that edge below.
    expect(at('label')?.left).toBe(44 + 120 + 18 + 16);
    expect(at('author')?.left).toBe(44);
  });

  it('centres a verse inside its panel and right-aligns a hadith', () => {
    const text = image(500, 60, 'text');
    const centred = placeFixed(
      WIDE,
      parts({ hadith: null, verse: { ...source(60, 'centre'), text } })
    );
    const aligned = placeFixed(WIDE, parts({ hadith: null, verse: { ...source(60), text } }));
    const textLeft = (placed: ReturnType<typeof placeFixed>) =>
      placed?.layers.find((layer) => layer.input.toString() === 'text')?.left;
    // Right-aligned text ends at the panel's inner right edge; centred text sits in the middle of the panel.
    expect(textLeft(aligned)).toBe(1200 - 44 - 5 - 24 - 500);
    expect(textLeft(centred)).toBe(44 + 24 + (1200 - 44 - 5 - 24 - 44 - 24 - 500) / 2);
  });

  it('measures a panel from its reference line and its text', () => {
    expect(panelHeight(source(100))).toBe(12 + 28 + 8 + 100 + 18);
  });

  it('paints a PNG of the placed size', async () => {
    const piece = await sharp({
      create: { width: 40, height: 20, channels: 4, background: '#fff' },
    })
      .png()
      .toBuffer();
    const png = await paint({
      width: 200,
      height: 100,
      layers: [{ input: piece, left: 10.4, top: 20.6 }],
    });
    const meta = await sharp(png).metadata();
    expect([meta.format, meta.width, meta.height]).toEqual(['png', 200, 100]);
  });
});
