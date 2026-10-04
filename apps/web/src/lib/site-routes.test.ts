import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';
import { AI_AGENTS } from './crawlers';
import { INDEXED_ROUTES, PRIVATE_PATHS, UNLISTED_ROUTES } from './seo';

interface SiteRoutes {
  INDEXED_ROUTES: string[];
  UNLISTED_ROUTES: string[];
  PRIVATE_PATHS: string[];
  AI_AGENTS: string[];
}

/** The check scripts are plain Node and cannot import TypeScript: they keep a copy, held equal here. */
describe('the routes of the SEO check scripts', () => {
  it('equal the lists of the app', async () => {
    const file = path.resolve(__dirname, '../../scripts/lib/site-routes.mjs');
    const copy = (await import(pathToFileURL(file).href)) as SiteRoutes;
    expect(copy.INDEXED_ROUTES).toEqual([...INDEXED_ROUTES]);
    expect(copy.UNLISTED_ROUTES).toEqual([...UNLISTED_ROUTES]);
    expect(copy.PRIVATE_PATHS).toEqual([...PRIVATE_PATHS]);
    expect(copy.AI_AGENTS).toEqual([...AI_AGENTS]);
  });
});
