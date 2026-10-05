import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

/*
 * Legibility (owner review, 4 October 2026): Reem Kufi is a display face. Set
 * small, its letters close up and «الحياة» reads «المياة». It is kept for
 * headings of 24 px and more; point labels, card and list
 * titles, section labels, buttons and chips use Readex Pro semibold.
 *
 * 24 px is also where WCAG 2.2 starts calling text large, so the display face
 * only ever appears where the 3:1 contrast rule of the gilded headings holds.
 */

const SRC = path.resolve(__dirname, '..');
const DISPLAY_MIN_PX = 24;
const REM_PX = 16;
const NAMED_SIZES_PX: Record<string, number> = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 36,
  '5xl': 48,
  '6xl': 60,
  // The product's own scale (app/globals.css).
  title: 28,
  'title-lg': 32,
  heading: 24,
  subheading: 20,
};

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) {
      return name === 'test' ? [] : sourceFiles(full);
    }
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

/** The font sizes a class string sets, in CSS pixels; the first one is the phone size. */
function sizesIn(classes: string): number[] {
  const sizes: number[] = [];
  for (const match of classes.matchAll(
    /(?:^|\s|:)text-(\[[\d.]+(?:rem|px)\]|[a-z0-9]+(?:-[a-z0-9]+)*)/g
  )) {
    const token = match[1] as string;
    const arbitrary = /^\[([\d.]+)(rem|px)\]$/.exec(token);
    if (arbitrary !== null) {
      const value = Number(arbitrary[1]);
      sizes.push(arbitrary[2] === 'rem' ? value * REM_PX : value);
    } else if (token in NAMED_SIZES_PX) {
      sizes.push(NAMED_SIZES_PX[token] as number);
    }
  }
  return sizes;
}

/** Every class string (a quoted literal) that names `class`, with its file. */
function classStringsWith(name: string): Array<{ file: string; classes: string }> {
  return sourceFiles(SRC).flatMap((file) => {
    const text = readFileSync(file, 'utf8');
    return Array.from(text.matchAll(/(['"`])([^'"`\n]*)\1/g))
      .map((match) => match[2] as string)
      .filter((classes) => classes.split(/\s+/).includes(name))
      .map((classes) => ({ file: path.relative(SRC, file), classes }));
  });
}

describe('the display face', () => {
  it('sets every display heading at 24 px or more, on the phone first', () => {
    const uses = classStringsWith('font-display');
    expect(uses.length).toBeGreaterThan(0);
    const small = uses.filter(({ classes }) => {
      const sizes = sizesIn(classes);
      return sizes.length === 0 || Math.min(...sizes) < DISPLAY_MIN_PX;
    });
    expect(small).toEqual([]);
  });

  it('is not the default of any heading', () => {
    const css = readFileSync(path.join(SRC, 'app/globals.css'), 'utf8');
    const headings = /h1,\s*h2,\s*h3\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(headings).toContain('font-family: var(--font-sans)');
    expect(headings).toContain('font-weight: 600');
    expect(css).not.toContain('--font-heading');
    expect(css).toContain('--font-display: var(--font-reem-kufi)');
  });

  it('sets no letter-spacing on Arabic text (docs/SEO.md §4)', () => {
    const tracked = sourceFiles(SRC).filter((file) =>
      /\btracking-/.test(readFileSync(file, 'utf8'))
    );
    expect(tracked.map((file) => path.relative(SRC, file))).toEqual([]);
  });
});

describe('sizesIn', () => {
  it('reads rem, px and named sizes, with or without a breakpoint', () => {
    expect(sizesIn('font-display text-[2.25rem] desktop:text-[3rem]')).toEqual([36, 48]);
    expect(sizesIn('text-[30px] text-2xl tablet:text-5xl')).toEqual([30, 24, 48]);
    expect(sizesIn('text-fg text-gilded text-center')).toEqual([]);
    expect(sizesIn('text-title tablet:text-title-lg text-heading')).toEqual([28, 32, 24]);
  });
});
