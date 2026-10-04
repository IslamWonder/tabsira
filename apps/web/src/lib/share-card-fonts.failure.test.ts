// @vitest-environment node
import { tmpdir } from 'node:os';
import { afterEach, describe, expect, it } from 'vitest';
import { cardFonts, coveredCodePoints } from './share-card-fonts';

const here = process.cwd();

afterEach(() => {
  process.chdir(here);
});

describe('the card fonts when the files are missing', () => {
  it('fail loudly, and try again on the next card instead of remembering the failure', async () => {
    process.chdir(tmpdir());
    await expect(coveredCodePoints()).rejects.toThrow(/ENOENT/);
    await expect(cardFonts()).rejects.toThrow(/ENOENT/);
    process.chdir(here);
    expect((await cardFonts()).length).toBe(4);
    expect((await coveredCodePoints()).size).toBeGreaterThan(100);
  });
});
