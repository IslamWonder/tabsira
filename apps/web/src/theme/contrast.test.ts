import { describe, expect, it } from 'vitest';
import { BLACK, composite, contrastRatio, parseColor, type Rgba, WHITE } from '@/test/contrast';
import { readTokens, type TokenSet } from '@/test/tokens';
import { THEME_BACKGROUND } from './colors';

/*
 * WCAG 2.2 AA for every text/background pair the components use, in both
 * themes, measured on the tokens as shipped (src/theme/tokens.css).
 *
 * A pair is a text token over a stack of surface tokens. Translucent surfaces
 * are composited over the page background, or, for text that sits on a photo,
 * over both pure white and pure black: the brightest and the darkest pixel a
 * photo can put behind it (tajriba §10).
 */

interface Pair {
  text: string;
  /** Surfaces from the bottom up, painted over the backdrop. */
  layers: readonly string[];
  backdrop?: 'page' | 'photo';
  /** Large text (24 px and up, or 18.66 px bold): 3:1 is enough. */
  large?: boolean;
}

const BODY_TEXT = [
  'text',
  'text-soft',
  'text-muted',
  'link',
  'primary',
  'danger',
  'secondary-fg',
  'step-title',
] as const;

const PAGE_SURFACES: readonly (readonly string[])[] = [
  [],
  ['surface'],
  ['surface-glass'],
  ['quran-surface-from'],
  ['quran-surface-to'],
  ['sunnah-surface-from'],
  ['sunnah-surface-to'],
  ['step-surface-from'],
  ['step-surface-to'],
];

const PAIRS: readonly Pair[] = [
  ...BODY_TEXT.flatMap((text) => PAGE_SURFACES.map((layers) => ({ text, layers }))),
  // Labels and chips on photos: glass over the photo's extremes.
  { text: 'glass-text', layers: ['surface-glass'], backdrop: 'photo' },
  { text: 'glass-text-soft', layers: ['surface-glass'], backdrop: 'photo' },
  // The floating navigation can float over a full-bleed photo.
  { text: 'nav-active', layers: ['nav-glass'], backdrop: 'photo' },
  { text: 'glass-text', layers: ['nav-glass'], backdrop: 'photo' },
  { text: 'glass-text-soft', layers: ['nav-glass'], backdrop: 'photo' },
  // Primary fill: both ends of the gradient.
  { text: 'on-primary', layers: ['primary-fill-from'] },
  { text: 'on-primary', layers: ['primary-fill-to'] },
  // The capture call: gold by day, emerald by night; both ends of its gradient.
  { text: 'on-cta', layers: ['cta-from'] },
  { text: 'on-cta', layers: ['cta-to'] },
  // Chips.
  { text: 'chip-primary-fg', layers: ['chip-primary-bg'] },
  { text: 'chip-primary-fg', layers: ['surface-glass', 'chip-primary-bg'] },
  // Evidence cards: labels, scripture, the Prophet's words.
  { text: 'quran-label', layers: ['quran-surface-from', 'quran-label-bg'] },
  { text: 'quran-label', layers: ['quran-surface-to', 'quran-label-bg'] },
  { text: 'sunnah-label', layers: ['sunnah-surface-from', 'sunnah-label-bg'] },
  { text: 'sunnah-label', layers: ['sunnah-surface-to', 'sunnah-label-bg'] },
  { text: 'quran-text', layers: ['quran-surface-from'] },
  { text: 'quran-text', layers: ['quran-surface-to'] },
  { text: 'hadith-words', layers: ['sunnah-surface-from'] },
  { text: 'hadith-words', layers: ['sunnah-surface-from', 'hadith-highlight'] },
  { text: 'hadith-words', layers: ['sunnah-surface-to', 'hadith-highlight'] },
  // The landing page: gold eyebrows and icons on the page and on cards, text on the example's band.
  { text: 'landing-gold', layers: [] },
  { text: 'landing-gold', layers: ['surface'] },
  { text: 'text', layers: ['landing-band'] },
  { text: 'text-soft', layers: ['landing-band'] },
  { text: 'text-soft', layers: ['landing-band', 'surface'] },
  // Large-text tokens: the ornate brackets ﴿ ﴾ are set at 26 px.
  { text: 'quran-accent', layers: ['quran-surface-from'], large: true },
  { text: 'quran-accent', layers: ['quran-surface-to'], large: true },
];

/** Non-text contrast (WCAG 1.4.11): the focus ring against what it is drawn on. */
const FOCUS_GROUNDS: readonly (readonly string[])[] = [[], ['surface'], ['surface-glass']];

/** Non-text contrast (WCAG 1.4.11): the edge of a field or a switch track, on the page and on a card. */
const FIELD_GROUNDS: readonly (readonly string[])[] = [
  ['surface'],
  ['surface', 'surface'],
  ['surface-glass', 'surface'],
  ['quran-surface-from', 'surface'],
];

function color(tokens: TokenSet, name: string): Rgba {
  const value = tokens[name];
  if (value === undefined) {
    throw new Error(`missing token --${name}`);
  }
  return parseColor(value);
}

function worstRatio(tokens: TokenSet, text: string, layers: readonly string[], backdrop = 'page') {
  const bases = backdrop === 'photo' ? [WHITE, BLACK] : [color(tokens, 'bg')];
  return Math.min(
    ...bases.map((base) => {
      const ground = layers.reduce((under, layer) => composite(color(tokens, layer), under), base);
      return contrastRatio(composite(color(tokens, text), ground), ground);
    })
  );
}

const { light, dark, darkSystem } = readTokens();
const THEMES = { light, dark } as const;

describe('design tokens', () => {
  it('defines the dark theme identically for the device setting and the explicit choice', () => {
    expect(darkSystem).toEqual(dark);
  });

  it('defines the same tokens in both themes', () => {
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
  });

  it('keeps the binding values of docs/DESIGN_DECISION.md', () => {
    const binding = {
      bg: ['#f6faf7', '#0b1210'],
      surface: ['#ffffff', 'rgba(255, 255, 255, 0.05)'],
      'surface-glass': ['rgba(255, 255, 255, 0.86)', 'rgba(20, 32, 28, 0.72)'],
      border: ['#dce7e1', 'rgba(255, 255, 255, 0.14)'],
      text: ['#16302a', '#eef3ef'],
      'text-soft': ['#4a635c', '#c3d4cc'],
      'text-muted': ['#5f6f69', '#93a79e'],
      primary: ['#0f4c3a', '#3fd69a'],
      'primary-fill-from': ['#0f4c3a', '#4fdca3'],
      'primary-fill-to': ['#0f4c3a', '#1f9e6e'],
      'on-primary': ['#ffffff', '#04130d'],
      'quran-accent': ['#9a7430', '#e6c77f'],
      'quran-surface-from': ['#eef7f2', 'rgba(230, 199, 127, 0.12)'],
      'quran-surface-to': ['#eef7f2', 'rgba(230, 199, 127, 0.03)'],
      'quran-border': ['#cfe6da', 'rgba(230, 199, 127, 0.32)'],
      'quran-label-bg': ['#0f4c3a', 'rgba(230, 199, 127, 0)'],
      'sunnah-accent': ['#7a5a1c', '#8feac2'],
      'sunnah-surface-from': ['#fbf8f0', 'rgba(63, 214, 154, 0.1)'],
      'sunnah-surface-to': ['#fbf8f0', 'rgba(63, 214, 154, 0.02)'],
      'sunnah-border': ['#efe4cb', 'rgba(63, 214, 154, 0.3)'],
      link: ['#0f4c3a', '#7fe3b8'],
      'glow-gold': ['#ffd978', '#e6c77f'],
      'glow-emerald': ['#0f4c3a', '#3fd69a'],
    } as const;
    for (const [token, [lightValue, darkValue]] of Object.entries(binding)) {
      expect(light[token], `light --${token}`).toBe(lightValue);
      expect(dark[token], `dark --${token}`).toBe(darkValue);
    }
  });

  it('gives the manifest and theme-color the page background of each theme', () => {
    expect(THEME_BACKGROUND.light.toLowerCase()).toBe(light.bg);
    expect(THEME_BACKGROUND.dark.toLowerCase()).toBe(dark.bg);
  });
});

describe.each(Object.entries(THEMES))('WCAG 2.2 AA contrast, %s theme', (theme, tokens) => {
  it.each(
    PAIRS.map((pair) => [
      `${pair.text} on ${pair.layers.join(' + ') || 'bg'}${pair.backdrop === 'photo' ? ' over a photo' : ''}`,
      pair,
    ])
  )('%s', (_name, pair) => {
    const { text, layers, backdrop, large } = pair as Pair;
    const ratio = worstRatio(tokens, text, layers, backdrop);
    if (process.env.CONTRAST_REPORT) {
      console.info(`${theme}\t${ratio.toFixed(2)}\t${large ? 'large' : 'normal'}\t${_name}`);
    }
    expect(ratio).toBeGreaterThanOrEqual(large ? 3 : 4.5);
  });

  it.each(FOCUS_GROUNDS.map((layers) => [layers.join(' + ') || 'bg', layers]))(
    'focus ring on %s reaches 3:1',
    (_name, layers) => {
      expect(worstRatio(tokens, 'focus', layers as readonly string[])).toBeGreaterThanOrEqual(3);
    }
  );
});

describe.each(Object.entries(THEMES))('field edges, %s theme', (_theme, tokens) => {
  it.each(FIELD_GROUNDS.map((layers) => [layers.join(' + '), layers]))(
    'field border on %s reaches 3:1',
    (_name, layers) => {
      expect(
        worstRatio(tokens, 'field-border', layers as readonly string[])
      ).toBeGreaterThanOrEqual(3);
    }
  );
});

describe.each(Object.entries(THEMES))('gilded headings, %s theme', (_theme, tokens) => {
  // Gilded headings are display headings, 24 px and up (src/theme/typography.test.ts): large
  // text, so 3:1 at every stop of the gradient.
  it('keeps every stop of the gilding at 3:1 on the page', () => {
    const stops = (tokens.gilded ?? '').match(/#[0-9a-f]{6}/g) ?? [];
    expect(stops.length).toBeGreaterThanOrEqual(3);
    for (const stop of stops) {
      expect(contrastRatio(parseColor(stop), color(tokens, 'bg'))).toBeGreaterThanOrEqual(3);
    }
  });
});

describe('the contrast helpers', () => {
  it('measure black on white as 21:1 and a colour on itself as 1:1', () => {
    expect(contrastRatio(BLACK, WHITE)).toBeCloseTo(21, 5);
    expect(contrastRatio(parseColor('#abc'), parseColor('#aabbcc'))).toBe(1);
  });

  it('reject what is not a colour', () => {
    expect(() => parseColor('var(--x)')).toThrow('not a colour');
    for (const text of [
      'rgb(1,2)',
      'rgba(1,2,3,)',
      'rgb(a,2,3)',
      'rgb(1 2 3)',
      'rgba(1,2,3,4,5)',
    ]) {
      expect(() => parseColor(text), text).toThrow('not a colour');
    }
  });

  it('read rgb and rgba with any spacing', () => {
    expect(parseColor(' RGB( 1 , 2.5,3 ) ')).toEqual({ r: 1, g: 2.5, b: 3, a: 1 });
    expect(parseColor('rgba(1,2,3, 0.5 )')).toEqual({ r: 1, g: 2, b: 3, a: 0.5 });
  });

  it('report a missing token by name', () => {
    expect(() => worstRatio({ bg: '#000000' }, 'nope', [])).toThrow('missing token --nope');
  });
});
