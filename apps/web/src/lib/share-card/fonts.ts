import path from 'node:path';

/*
 * The faces of the share card, read from this repository's own files and never
 * from a network: the Quran in the unmodified KFGQPC file, the rest in Readex
 * Pro as in the pages. The text engine (Pango, inside sharp) reads TrueType and
 * OpenType files but not WOFF, so the Readex Pro faces are kept in this
 * repository as plain TrueType files made from the package's own WOFF files by
 * `pnpm --filter @tabsira/web gen:card-fonts` (tables inflated, none edited).
 * next.config.ts lists the files for the output trace, so a standalone build
 * carries them. Licences and sources: src/fonts/README.md.
 */

export interface Face {
  /** The family name inside the file, as the text engine knows it. */
  readonly family: string;
  /** Path of a TrueType file. */
  readonly file: string;
}

export interface CardFaces {
  /** The Arabic and Latin subsets of Readex Pro, regular and semi-bold. */
  readonly text: readonly Face[];
  readonly quran: Face;
}

export const TEXT_FAMILY = 'Readex Pro';
export const QURAN_FAMILY = 'KFGQPC HAFS Uthmanic Script';

/** Relative to the web app's folder, which is the working directory of the server. */
export const QURAN_SOURCE = 'src/fonts/UthmanicHafs_V22.ttf';
export const TEXT_SOURCES: readonly string[] = [
  'src/fonts/card/readex-pro-arabic-400-normal.ttf',
  'src/fonts/card/readex-pro-arabic-600-normal.ttf',
  // Latin letters, digits and the ASCII punctuation, which the Arabic subset lacks.
  'src/fonts/card/readex-pro-latin-400-normal.ttf',
  'src/fonts/card/readex-pro-latin-600-normal.ttf',
];

export function cardFaces(): CardFaces {
  // The files are named for the build in next.config.ts (outputFileTracingIncludes): the tracer
  // must not follow this path, or it copies the whole project into the standalone output.
  const at = (source: string) => path.join(/* turbopackIgnore: true */ process.cwd(), source);
  return {
    text: TEXT_SOURCES.map((source) => ({ family: TEXT_FAMILY, file: at(source) })),
    quran: { family: QURAN_FAMILY, file: at(QURAN_SOURCE) },
  };
}
