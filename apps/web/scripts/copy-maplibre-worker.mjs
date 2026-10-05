/**
 * MapLibre GL 6 starts its worker from a file it looks for next to its own
 * module (`import.meta.url`). Once the app is bundled that address is the
 * page's, so the browser loads the page as the worker and refuses it
 * (Firefox: NS_ERROR_CORRUPTED_CONTENT). The map names
 * /maplibre/maplibre-gl-worker.mjs instead (`MAPLIBRE_WORKER_URL`), and this
 * script copies that file and the shared module it imports from the
 * installed package into public/maplibre before every dev start and build.
 * The copies are never committed (.gitignore).
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const dist = path.join(path.dirname(require.resolve('maplibre-gl/package.json')), 'dist');
const to = path.join(here, '..', 'public', 'maplibre');
const files = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs'];

mkdirSync(to, { recursive: true });
for (const file of files) {
  copyFileSync(path.join(dist, file), path.join(to, file));
}
console.log(`maplibre worker copied to public/maplibre (${files.length} files)`);
