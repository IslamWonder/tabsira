import { readdirSync } from 'node:fs';
import path from 'node:path';
// The matcher Next itself uses for `headers()` sources.
import { pathToRegexp } from 'next/dist/compiled/path-to-regexp';
import { describe, expect, it } from 'vitest';
import { PICTURE_CACHE_RULES, PICTURE_FOLDERS } from './cache-headers';

const PUBLIC = path.resolve(__dirname, '../../public');
const APP = path.resolve(__dirname, '../app');

const matches = (pathname: string) =>
  PICTURE_CACHE_RULES.some((rule) => pathToRegexp(rule.source, [], {}).test(pathname));

describe('PICTURE_CACHE_RULES', () => {
  it('caches every decorative picture for a year', () => {
    for (const folder of PICTURE_FOLDERS) {
      const files = readdirSync(path.join(PUBLIC, folder));
      expect(files.length).toBeGreaterThan(0);
      for (const file of files) {
        expect(matches(`/${folder}/${file}`), `/${folder}/${file}`).toBe(true);
      }
    }
    expect(PICTURE_CACHE_RULES[0]?.headers).toEqual([
      { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
    ]);
  });

  it("never matches a page: the reader's world and any route of the same name", () => {
    for (const pathname of [
      '/world',
      '/world/',
      '/landing',
      '/scene',
      '/world/7000000000000000001',
    ]) {
      expect(matches(pathname), pathname).toBe(false);
    }
    // Nor any route the app has under those names.
    for (const folder of PICTURE_FOLDERS) {
      const route = path.join(APP, folder);
      const children = readdirSync(APP).includes(folder) ? readdirSync(route) : [];
      for (const child of children.filter((name) => !name.includes('.'))) {
        expect(matches(`/${folder}/${child}`), `/${folder}/${child}`).toBe(false);
      }
    }
  });
});
