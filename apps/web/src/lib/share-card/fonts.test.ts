// @vitest-environment node
import { readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { cardFaces, QURAN_SOURCE, TEXT_SOURCES, woffToSfnt } from './fonts';

const SFNT_TRUETYPE = 0x00010000;

describe('the faces of the share card', () => {
  it('unpacks a WOFF into the same tables as a plain SFNT file', async () => {
    const woff = await readFile(path.join(process.cwd(), TEXT_SOURCES[0] as string));
    const sfnt = woffToSfnt(woff);
    expect(sfnt.readUInt32BE(0)).toBe(woff.readUInt32BE(4));
    expect(sfnt.readUInt16BE(4)).toBe(woff.readUInt16BE(12));
    // Every table directory entry points inside the file and the file is whole words.
    const count = sfnt.readUInt16BE(4);
    for (let index = 0; index < count; index += 1) {
      const at = 12 + index * 16;
      expect(sfnt.readUInt32BE(at + 8) + sfnt.readUInt32BE(at + 12)).toBeLessThanOrEqual(
        sfnt.length
      );
    }
    expect(sfnt.length % 4).toBe(0);
    expect([SFNT_TRUETYPE, 0x4f54544f]).toContain(sfnt.readUInt32BE(0));
  });

  it('keeps a table that the WOFF stored uncompressed', () => {
    const table = Buffer.from('abcdefgh');
    const woff = Buffer.alloc(44 + 20);
    woff.write('wOFF', 0, 'latin1');
    woff.writeUInt32BE(SFNT_TRUETYPE, 4);
    woff.writeUInt16BE(1, 12);
    woff.write('test', 44, 'latin1');
    woff.writeUInt32BE(64, 48);
    woff.writeUInt32BE(table.length, 52);
    woff.writeUInt32BE(table.length, 56);
    const sfnt = woffToSfnt(Buffer.concat([woff, table]));
    expect(sfnt.subarray(28).toString()).toBe('abcdefgh');
  });

  it('names the Quran face from the repository file and the text faces from unpacked copies', async () => {
    const faces = await cardFaces();
    expect(faces.quran.file).toBe(path.join(process.cwd(), QURAN_SOURCE));
    expect(faces.text).toHaveLength(TEXT_SOURCES.length);
    for (const face of faces.text) {
      expect(face.file.startsWith(os.tmpdir())).toBe(true);
      expect((await readFile(face.file)).readUInt32BE(0)).toBe(SFNT_TRUETYPE);
    }
    expect(await cardFaces()).toBe(faces);
  });

  it('unpacks again after the folder is gone, and tries again after a failure', async () => {
    const { cardFaces: fresh } = await freshModule();
    const first = await fresh();
    await rm(path.dirname(first.text[0]?.file as string), { recursive: true, force: true });
    const { cardFaces: second } = await freshModule();
    expect((await second()).text[0]?.file).toBe(first.text[0]?.file);
    expect((await readFile(first.text[0]?.file as string)).length).toBeGreaterThan(0);

    const { cardFaces: failing } = await freshModule();
    const cwd = vi.spyOn(process, 'cwd').mockReturnValue('/nonexistent-tabsira-folder');
    await expect(failing()).rejects.toThrow();
    cwd.mockRestore();
    expect((await failing()).quran.file).toBe(path.join(process.cwd(), QURAN_SOURCE));
  });
});

async function freshModule() {
  vi.resetModules();
  return import('./fonts');
}
