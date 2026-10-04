// The Readex Pro faces of the share card, as the plain TrueType files its text
// engine reads (it does not read WOFF). Each is the WOFF file of the pinned
// @fontsource package with its tables inflated and laid out one after the other:
// no table is edited and the names inside stay the font's own. The SIL Open Font
// License travels beside them. Run after the package is updated:
//
//   pnpm --filter @tabsira/web gen:card-fonts

import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { inflateSync } from 'node:zlib';

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PACKAGE = path.join(WEB, 'node_modules/@fontsource/readex-pro');
const TARGET = path.join(WEB, 'src/fonts/card');
const FACES = [
  ['arabic', 400],
  ['arabic', 600],
  ['latin', 400],
  ['latin', 600],
];

const WOFF_HEADER = 44;
const WOFF_ENTRY = 20;
const SFNT_HEADER = 12;
const SFNT_ENTRY = 16;

function readTables(woff) {
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

function woffToSfnt(woff) {
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

await mkdir(TARGET, { recursive: true });
for (const [subset, weight] of FACES) {
  const name = `readex-pro-${subset}-${weight}-normal`;
  const woff = await readFile(path.join(PACKAGE, 'files', `${name}.woff`));
  await writeFile(path.join(TARGET, `${name}.ttf`), woffToSfnt(woff));
}
await copyFile(path.join(PACKAGE, 'LICENSE'), path.join(TARGET, 'readex-pro-LICENSE.txt'));
