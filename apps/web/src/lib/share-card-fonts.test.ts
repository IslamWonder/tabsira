// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
  canDraw,
  cardFonts,
  cmapTable,
  codePointsOf,
  coveredCodePoints,
  drawable,
  LATIN_FONT,
  UI_FONT,
} from './share-card-fonts';

describe('the card fonts', () => {
  it('load once and cover Arabic, Latin and digits, so no character is fetched elsewhere', async () => {
    const fonts = await cardFonts();
    expect(fonts.map((font) => [font.name, font.weight])).toEqual([
      [UI_FONT, 500],
      [UI_FONT, 600],
      [LATIN_FONT, 500],
      [LATIN_FONT, 600],
    ]);
    expect(await cardFonts()).toBe(fonts);
    const covered = await coveredCodePoints();
    expect(await coveredCodePoints()).toBe(covered);
    expect(canDraw('عنوان البصيرة، الآية 50 tabsira.me/i/12 «شرح»', covered)).toBe(true);
    expect(canDraw('😀', covered)).toBe(false);
    expect(canDraw('中文', covered)).toBe(false);
    expect(drawable('عنوان 😀 中 tabsira', covered)).toBe('عنوان   tabsira');
  });

  it('reads the character map of a WOFF and refuses a file without one', async () => {
    const fonts = await cardFonts();
    const plex = fonts[0] as (typeof fonts)[number];
    const codes = codePointsOf(plex.data);
    expect(codes.has('ع'.codePointAt(0) as number)).toBe(true);
    expect(codes.has(0x1f600)).toBe(false);
    expect(cmapTable(plex.data).byteLength).toBeGreaterThan(0);
    const bare = new ArrayBuffer(64);
    new DataView(bare).setUint32(0, 0x00010000);
    expect(() => cmapTable(bare)).toThrow(/cmap/);
    const woff = new ArrayBuffer(64);
    new DataView(woff).setUint32(0, 0x774f4646);
    expect(() => cmapTable(woff)).toThrow(/cmap/);
  });
});
