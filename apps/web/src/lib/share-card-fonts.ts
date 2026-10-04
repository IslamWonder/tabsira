import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { inflateSync } from 'node:zlib';

/*
 * The fonts the share card is drawn with, and the characters they cover.
 *
 * The image renderer takes raw font files and, for any character none of them
 * has, fetches a font from Google: a third-party call our server never makes
 * (AGENTS.md). So the card is drawn only with characters these files cover,
 * which `coveredCodePoints` reads from their own character maps: platform text
 * loses an uncovered character, scripture is never altered and gives way to its
 * reference instead (share-card.tsx). IBM Plex Sans Arabic is the one card face
 * of docs/SEO.md §2. The renderer cannot parse Reem Kufi, Noto Naskh or Amiri,
 * and it drops vowel marks and misjoins letters, which is why the card never
 * draws Quran or hadith text and needs no Quran face.
 */

export interface CardFont {
  name: string;
  data: ArrayBuffer;
  weight: 400 | 500 | 600 | 700;
  style: 'normal';
}

export const UI_FONT = 'IBM Plex Sans Arabic';
/** The Latin subset under its own family name: the renderer keeps one file per family and weight. */
export const LATIN_FONT = 'IBM Plex Sans Arabic Latin';
/** What every text node of the card is set in: the Arabic face, then its Latin subset. */
export const CARD_FONT_FAMILY = `${UI_FONT}, ${LATIN_FONT}`;

const PLEX = 'node_modules/@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic';
export const CARD_FONT_FILES: readonly {
  name: string;
  weight: CardFont['weight'];
  file: string;
}[] = [
  { name: UI_FONT, weight: 500, file: `${PLEX}-arabic-500-normal.woff` },
  { name: UI_FONT, weight: 600, file: `${PLEX}-arabic-600-normal.woff` },
  { name: LATIN_FONT, weight: 500, file: `${PLEX}-latin-500-normal.woff` },
  { name: LATIN_FONT, weight: 600, file: `${PLEX}-latin-600-normal.woff` },
];

async function read(relative: string): Promise<ArrayBuffer> {
  const buffer = await readFile(path.join(process.cwd(), relative));
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
}

let loaded: Promise<CardFont[]> | undefined;

/** The fonts, read on the first card and kept for the process; a failed read is tried again. */
export function cardFonts(): Promise<CardFont[]> {
  loaded ??= Promise.all(
    CARD_FONT_FILES.map(async ({ name, weight, file }) => ({
      name,
      weight,
      style: 'normal' as const,
      data: await read(file),
    }))
  ).catch((error: unknown) => {
    loaded = undefined;
    throw error;
  });
  return loaded;
}

// ─── Character maps ───────────────────────────────────────────────────────────

/** The `cmap` table of a TrueType or WOFF font, as raw bytes. */
export function cmapTable(font: ArrayBuffer): DataView {
  const view = new DataView(font);
  const tag = view.getUint32(0);
  if (tag === 0x774f4646) {
    // 'wOFF': each table is deflated on its own.
    const count = view.getUint16(12);
    for (let i = 0; i < count; i += 1) {
      const at = 44 + i * 20;
      if (view.getUint32(at) === 0x636d6170) {
        const offset = view.getUint32(at + 4);
        const compressed = view.getUint32(at + 8);
        const original = view.getUint32(at + 12);
        const bytes = new Uint8Array(font, offset, compressed);
        const table = compressed === original ? bytes : new Uint8Array(inflateSync(bytes));
        return new DataView(table.buffer, table.byteOffset, table.byteLength);
      }
    }
  } else {
    const count = view.getUint16(4);
    for (let i = 0; i < count; i += 1) {
      const at = 12 + i * 16;
      if (view.getUint32(at) === 0x636d6170) {
        return new DataView(font, view.getUint32(at + 8), view.getUint32(at + 12));
      }
    }
  }
  throw new Error('font without a cmap table');
}

function addFormat4(table: DataView, at: number, into: Set<number>): void {
  const segments = table.getUint16(at + 6) / 2;
  const ends = at + 14;
  const starts = ends + segments * 2 + 2;
  for (let i = 0; i < segments; i += 1) {
    const end = table.getUint16(ends + i * 2);
    const start = table.getUint16(starts + i * 2);
    if (start === 0xffff) {
      continue;
    }
    for (let code = start; code <= end; code += 1) {
      into.add(code);
    }
  }
}

function addFormat12(table: DataView, at: number, into: Set<number>): void {
  const groups = table.getUint32(at + 12);
  for (let i = 0; i < groups; i += 1) {
    const group = at + 16 + i * 12;
    const start = table.getUint32(group);
    const end = table.getUint32(group + 4);
    for (let code = start; code <= end; code += 1) {
      into.add(code);
    }
  }
}

/** Every code point a font maps to a glyph (Unicode subtables, formats 4 and 12). */
export function codePointsOf(font: ArrayBuffer): Set<number> {
  const table = cmapTable(font);
  const covered = new Set<number>();
  const subtables = table.getUint16(2);
  for (let i = 0; i < subtables; i += 1) {
    const record = 4 + i * 8;
    const platform = table.getUint16(record);
    if (platform !== 0 && platform !== 3) {
      continue;
    }
    const at = table.getUint32(record + 4);
    const format = table.getUint16(at);
    if (format === 4) {
      addFormat4(table, at, covered);
    } else if (format === 12) {
      addFormat12(table, at, covered);
    }
  }
  return covered;
}

let coverage: Promise<Set<number>> | undefined;

/** The union of the characters the card fonts cover, computed once. */
export function coveredCodePoints(): Promise<Set<number>> {
  coverage ??= cardFonts()
    .then((fonts) => {
      const all = new Set<number>();
      for (const font of fonts) {
        for (const code of codePointsOf(font.data)) {
          all.add(code);
        }
      }
      return all;
    })
    .catch((error: unknown) => {
      coverage = undefined;
      throw error;
    });
  return coverage;
}

/** Whitespace the renderer handles without a glyph. */
const BLANK = /\s/u;

/** Whether every character of `text` has a glyph in the card fonts. */
export function canDraw(text: string, covered: ReadonlySet<number>): boolean {
  for (const character of text) {
    if (!BLANK.test(character) && !covered.has(character.codePointAt(0) as number)) {
      return false;
    }
  }
  return true;
}

/** A platform text without the characters the fonts lack (never used on scripture). */
export function drawable(text: string, covered: ReadonlySet<number>): string {
  return Array.from(text)
    .filter((character) => BLANK.test(character) || covered.has(character.codePointAt(0) as number))
    .join('');
}
