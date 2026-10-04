// @vitest-environment node
import { deflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import { cmapTable, codePointsOf } from './share-card-fonts';

/*
 * Synthetic fonts, so the character-map reader is checked on every layout it
 * accepts: a TrueType file with a format 12 subtable and a skipped Macintosh
 * record, and a WOFF whose table is stored once deflated and once as is.
 */

function u16(...values: number[]): Uint8Array {
  const out = new Uint8Array(values.length * 2);
  const view = new DataView(out.buffer);
  for (const [i, value] of values.entries()) {
    view.setUint16(i * 2, value);
  }
  return out;
}

function u32(...values: number[]): Uint8Array {
  const out = new Uint8Array(values.length * 4);
  const view = new DataView(out.buffer);
  for (const [i, value] of values.entries()) {
    view.setUint32(i * 4, value);
  }
  return out;
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, part) => n + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

const TAG_CMAP = 0x636d6170;

/**
 * A cmap table: a Macintosh record (skipped), a format 12 subtable, a format 4
 * one with the end segment, and a format 0 subtable the reader does not use.
 */
function cmap(): Uint8Array {
  const header = concat(u16(0, 4));
  const records = 4 * 8;
  const format12At = 4 + records;
  const format12 = concat(u16(12, 0), u32(16 + 12, 0, 1), u32(0x1f600, 0x1f601, 1));
  const format4At = format12At + format12.length;
  // Two segments: ع..غ (U+0639..U+063A) and the required 0xFFFF end segment.
  const format4 = concat(
    u16(4, 16 + 4 * 2 * 2, 0, 4, 0, 0, 0),
    u16(0x063a, 0xffff),
    u16(0),
    u16(0x0639, 0xffff),
    u16(0, 1),
    u16(0, 0)
  );
  const format0At = format4At + format4.length;
  const format0 = u16(0, 6, 0);
  return concat(
    header,
    u16(1, 0),
    u32(format4At),
    u16(0, 3),
    u32(format12At),
    u16(3, 1),
    u32(format4At),
    u16(0, 0),
    u32(format0At),
    format12,
    format4,
    format0
  );
}

/** A TrueType file with a `head` table before the `cmap` one. */
function trueType(table: Uint8Array): ArrayBuffer {
  const offset = 12 + 2 * 16;
  const head = u32(0, 0, 0, 0);
  const file = concat(
    u32(0x00010000),
    u16(2, 0, 0, 0),
    u32(0x68656164, 0, offset, head.length),
    u32(TAG_CMAP, 0, offset + head.length, table.length),
    head,
    table
  );
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer;
}

function woff(table: Uint8Array, compress: boolean): ArrayBuffer {
  const stored = compress ? new Uint8Array(deflateSync(table)) : table;
  const offset = 44 + 20;
  const file = concat(
    u32(0x774f4646, 0x00010000, offset + stored.length),
    u16(1, 0),
    u32(0),
    u16(0, 0),
    u32(0, 0, 0, 0, 0),
    u32(TAG_CMAP, offset, stored.length, table.length, 0),
    stored
  );
  return file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength) as ArrayBuffer;
}

describe('the character-map reader', () => {
  it('reads format 4 and format 12 subtables of a TrueType file, skipping non-Unicode records', () => {
    const codes = codePointsOf(trueType(cmap()));
    expect(codes.has(0x0639)).toBe(true);
    expect(codes.has(0x063a)).toBe(true);
    expect(codes.has(0x063b)).toBe(false);
    expect(codes.has(0x1f600)).toBe(true);
    expect(codes.has(0x1f601)).toBe(true);
    expect(codes.has(0xffff)).toBe(false);
  });

  it('reads a WOFF table whether it is deflated or stored as is', () => {
    for (const compress of [true, false]) {
      const codes = codePointsOf(woff(cmap(), compress));
      expect(codes.has(0x0639)).toBe(true);
      expect(codes.has(0x1f601)).toBe(true);
    }
    expect(cmapTable(woff(cmap(), true)).byteLength).toBe(cmap().length);
  });
});
