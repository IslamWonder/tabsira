import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { inflateSync } from 'node:zlib';

/*
 * The faces of the share card, read from this repository's own files (never a
 * network): the Quran in the unmodified KFGQPC file (src/fonts/README.md), the
 * rest in Readex Pro from the pinned @fontsource package, as in the pages.
 *
 * The text engine (Pango, inside sharp) reads TrueType and OpenType files but
 * not WOFF, which is what the package ships next to its WOFF2. A WOFF 1 file is
 * the same tables, each deflated, so each face is unpacked once into the
 * operating system's temporary folder and registered from there; no table is
 * edited and the names inside stay the font's own. next.config.ts lists the
 * source files for the output trace so a standalone build carries them.
 */

export interface Face {
  /** The family name inside the file, as the text engine knows it. */
  readonly family: string;
  /** Path of a TrueType or OpenType file. */
  readonly file: string;
}

export interface CardFaces {
  /** The Arabic and Latin subsets of Readex Pro, regular and semi-bold. */
  readonly text: readonly Face[];
  readonly quran: Face;
}

export const TEXT_FAMILY = 'Readex Pro';
export const QURAN_FAMILY = 'KFGQPC HAFS Uthmanic Script';

const PACKAGE = 'node_modules/@fontsource/readex-pro/files';
export const TEXT_SOURCES: readonly string[] = [
  `${PACKAGE}/readex-pro-arabic-400-normal.woff`,
  `${PACKAGE}/readex-pro-arabic-600-normal.woff`,
  // Latin letters, digits and the ASCII punctuation, which the Arabic subset lacks.
  `${PACKAGE}/readex-pro-latin-400-normal.woff`,
  `${PACKAGE}/readex-pro-latin-600-normal.woff`,
];
export const QURAN_SOURCE = 'src/fonts/UthmanicHafs_V22.ttf';

const WOFF_HEADER = 44;
const WOFF_ENTRY = 20;
const SFNT_HEADER = 12;
const SFNT_ENTRY = 16;

interface Table {
  tag: Buffer;
  checksum: number;
  length: number;
  data: Buffer;
}

function readTables(woff: Buffer): Table[] {
  const count = woff.readUInt16BE(12);
  return Array.from({ length: count }, (_, index) => {
    const at = WOFF_HEADER + index * WOFF_ENTRY;
    const offset = woff.readUInt32BE(at + 4);
    const stored = woff.readUInt32BE(at + 8);
    const length = woff.readUInt32BE(at + 12);
    const raw = woff.subarray(offset, offset + stored);
    return {
      tag: woff.subarray(at, at + 4),
      checksum: woff.readUInt32BE(at + 16),
      length,
      // A table kept as it is has equal stored and original lengths.
      data: stored < length ? inflateSync(raw) : raw,
    };
  });
}

/** The same font as a plain SFNT file: the tables inflated and laid out one after the other. */
export function woffToSfnt(woff: Buffer): Buffer {
  const tables = readTables(woff);
  const count = tables.length;
  const header = Buffer.alloc(SFNT_HEADER + count * SFNT_ENTRY);
  header.writeUInt32BE(woff.readUInt32BE(4), 0);
  header.writeUInt16BE(count, 4);
  const log = Math.floor(Math.log2(count));
  header.writeUInt16BE(2 ** log * 16, 6);
  header.writeUInt16BE(log, 8);
  header.writeUInt16BE(count * 16 - 2 ** log * 16, 10);
  let offset = header.length;
  const body = tables.map((table, index) => {
    const at = SFNT_HEADER + index * SFNT_ENTRY;
    table.tag.copy(header, at);
    header.writeUInt32BE(table.checksum, at + 4);
    header.writeUInt32BE(offset, at + 8);
    header.writeUInt32BE(table.length, at + 12);
    const padded = Buffer.concat([table.data, Buffer.alloc((4 - (table.data.length % 4)) % 4)]);
    offset += padded.length;
    return padded;
  });
  return Buffer.concat([header, ...body]);
}

function folder(): string {
  return path.join(os.tmpdir(), 'tabsira-share-card-fonts');
}

async function exists(file: string): Promise<boolean> {
  return stat(file).then(
    () => true,
    () => false
  );
}

/** Unpacks one source file into the temporary folder, under a name made of its content, once. */
async function unpack(source: string): Promise<string> {
  const woff = await readFile(path.join(process.cwd(), source));
  const sfnt = woffToSfnt(woff);
  const name = createHash('sha256').update(sfnt).digest('hex').slice(0, 16);
  const file = path.join(folder(), `${name}.ttf`);
  if (!(await exists(file))) {
    await mkdir(folder(), { recursive: true });
    // Written beside and renamed, so a second worker never reads half a file.
    const partial = `${file}.${process.pid}`;
    await writeFile(partial, sfnt);
    await rename(partial, file);
  }
  return file;
}

let loaded: Promise<CardFaces> | undefined;

async function load(): Promise<CardFaces> {
  const [text, quran] = await Promise.all([
    Promise.all(TEXT_SOURCES.map(unpack)),
    Promise.resolve(path.join(process.cwd(), QURAN_SOURCE)),
  ]);
  return {
    text: text.map((file) => ({ family: TEXT_FAMILY, file })),
    quran: { family: QURAN_FAMILY, file: quran },
  };
}

/** The faces, prepared once per process; a failure is tried again on the next request. */
export function cardFaces(): Promise<CardFaces> {
  loaded ??= load().catch((error: unknown) => {
    loaded = undefined;
    throw error;
  });
  return loaded;
}
