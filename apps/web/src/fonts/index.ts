import localFont from 'next/font/local';

/*
 * Every face is served from this app (AGENTS.md: no third-party request from the
 * visitor's browser). The OFL faces come from the pinned @fontsource packages,
 * the Quran face is the unmodified KFGQPC file next to this module. Licences and
 * sources: ./README.md.
 *
 * Only the weights the interface uses are declared. The interface faces are
 * preloaded; the scripture and ornament faces load when an evidence card first
 * needs them, so the first screen does not wait for them.
 *
 * next/font reads these options at build time, so every value is a literal.
 */

/** Interface text, Arabic glyphs. */
export const readexArabic = localFont({
  src: [
    {
      path: '../../node_modules/@fontsource/readex-pro/files/readex-pro-arabic-400-normal.woff2',
      weight: '400',
    },
    {
      path: '../../node_modules/@fontsource/readex-pro/files/readex-pro-arabic-500-normal.woff2',
      weight: '500',
    },
    {
      path: '../../node_modules/@fontsource/readex-pro/files/readex-pro-arabic-600-normal.woff2',
      weight: '600',
    },
  ],
  variable: '--font-readex-arabic',
  display: 'swap',
  adjustFontFallback: false,
});

/** Interface text, Latin glyphs and digits the Arabic subset lacks; loads only when such text appears. */
export const readexLatin = localFont({
  src: [
    {
      path: '../../node_modules/@fontsource/readex-pro/files/readex-pro-latin-400-normal.woff2',
      weight: '400',
    },
    {
      path: '../../node_modules/@fontsource/readex-pro/files/readex-pro-latin-600-normal.woff2',
      weight: '600',
    },
  ],
  variable: '--font-readex-latin',
  display: 'swap',
  preload: false,
  adjustFontFallback: false,
});

/**
 * Display headings of 24 px and more, bold only. Smaller text
 * uses Readex Pro: set small, Reem Kufi's letters close up (src/theme/typography.test.ts).
 */
export const reemKufi = localFont({
  src: [
    {
      path: '../../node_modules/@fontsource/reem-kufi/files/reem-kufi-arabic-700-normal.woff2',
      weight: '700',
    },
  ],
  variable: '--font-reem-kufi',
  display: 'swap',
  adjustFontFallback: false,
});

/** Hadith text: regular for the chain and the body, bold for the Prophet's words. */
export const notoNaskh = localFont({
  src: [
    {
      path: '../../node_modules/@fontsource/noto-naskh-arabic/files/noto-naskh-arabic-arabic-400-normal.woff2',
      weight: '400',
    },
    {
      path: '../../node_modules/@fontsource/noto-naskh-arabic/files/noto-naskh-arabic-arabic-700-normal.woff2',
      weight: '700',
    },
  ],
  variable: '--font-noto-naskh',
  display: 'swap',
  preload: false,
  adjustFontFallback: false,
});

/** The ornate brackets (U+FD3E, U+FD3F) only: the unicode-range keeps the browser from using it for anything else. */
export const amiri = localFont({
  src: [
    {
      path: '../../node_modules/@fontsource/amiri/files/amiri-arabic-400-normal.woff2',
      weight: '400',
    },
  ],
  variable: '--font-amiri',
  display: 'swap',
  preload: false,
  adjustFontFallback: false,
  declarations: [{ prop: 'unicode-range', value: 'U+FD3E-FD3F' }],
});

/** KFGQPC HAFS Uthmanic Script v2.2, unmodified (its licence forbids any change, conversion included). */
export const uthmanicHafs = localFont({
  src: [{ path: './UthmanicHafs_V22.ttf', weight: '400' }],
  variable: '--font-uthmanic-hafs',
  display: 'swap',
  preload: false,
  adjustFontFallback: false,
});

/** Class names that define every font variable; set once on <html>. */
export const fontVariables = [readexArabic, readexLatin, reemKufi, notoNaskh, amiri, uthmanicHafs]
  .map((font) => font.variable)
  .join(' ');
