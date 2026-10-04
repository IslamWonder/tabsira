// @vitest-environment node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { cardFaces, QURAN_FAMILY, QURAN_SOURCE, TEXT_FAMILY, TEXT_SOURCES } from './fonts';

const TRUETYPE = 0x00010000;

describe('the faces of the share card', () => {
  it('are files of this repository, TrueType, that exist', async () => {
    const faces = cardFaces();
    expect(faces.text).toHaveLength(TEXT_SOURCES.length);
    expect(faces.text.every((face) => face.family === TEXT_FAMILY)).toBe(true);
    expect(faces.quran).toEqual({
      family: QURAN_FAMILY,
      file: path.join(process.cwd(), QURAN_SOURCE),
    });
    for (const face of [...faces.text, faces.quran]) {
      expect((await readFile(face.file)).readUInt32BE(0)).toBe(TRUETYPE);
    }
  });

  it('carry the licence of the faces made from a package beside them', async () => {
    const licence = await readFile(
      path.join(process.cwd(), 'src/fonts/card/readex-pro-LICENSE.txt'),
      'utf8'
    );
    expect(licence).toContain('SIL Open Font License, Version 1.1');
  });
});
