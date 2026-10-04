#!/usr/bin/env node
/**
 * Tell Bing, Yandex, Naver, Seznam, Yep and Amazon what changed (IndexNow).
 *
 * One POST to api.indexnow.org reaches them all; Google does not take part and reads the
 * sitemap. Written against the protocol, no package (docs/SEO.md, section 5):
 *
 * - Production only. It refuses to run unless SITE_URL is https://tabsira.me, or --force is
 *   given: a staging or development machine must never announce its addresses. Refusing is a
 *   warning and exit code 0, like every other way of not submitting.
 * - Only what changed. Each sitemap URL, with the lastmod it was sent with, is remembered in
 *   INDEXNOW_STATE (a file outside the release folder, so a deploy does not forget it and does
 *   not resubmit the whole site, which the protocol answers with 429). A URL with no lastmod
 *   is sent once, when it first appears. Only URLs of SITE_URL are ever sent.
 * - The key is the one file in apps/web/public named after its own contents, committed so a
 *   clean checkout never forces re-verification. `--init` makes it, and does nothing when it
 *   already exists.
 * - Run last in a production deploy, after nginx has reloaded and the site answers: engines
 *   fetch what they are handed.
 * - A failure prints a warning and exits 0: the site is live and correct, and the sitemap
 *   carries the same news at crawl speed.
 *
 * Usage: node scripts/indexnow.mjs [--init] [--dry-run] [--force]
 *   SITE_URL        the public address; must be https://tabsira.me unless --force
 *   SITEMAP_URL     where to read the sitemap (default http://127.0.0.1:3000/sitemap.xml)
 *   INDEXNOW_STATE  what was sent (default ~/.local/state/tabsira/indexnow.json); must be outside
 *                   the release folder
 */
import { randomBytes } from 'node:crypto';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ENDPOINT = 'https://api.indexnow.org/indexnow';
/** The protocol's ceiling per request. */
export const BATCH = 10000;
export const PRODUCTION_SITE = 'https://tabsira.me';
/** Seconds to wait for any one request: a deploy never hangs on a search engine. */
export const TIMEOUT_MS = 15000;

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const KEY_FILE = /^([A-Za-z0-9-]{8,128})\.txt$/;

/** The keys on offer: the public files whose name (without .txt) is also their contents. */
export async function findKeys(publicDir) {
  const keys = [];
  for (const name of await readdir(publicDir)) {
    const match = KEY_FILE.exec(name);
    if (!match) continue;
    const contents = (await readFile(join(publicDir, name), 'utf8')).trim();
    if (contents === match[1]) keys.push(contents);
  }
  return keys;
}

/** The key: exactly one such file, or an error that says what is wrong. */
export async function findKey(publicDir) {
  const keys = await findKeys(publicDir);
  if (keys.length !== 1) {
    throw new Error(`expected one IndexNow key file in ${publicDir}, found ${keys.length}`);
  }
  return keys[0];
}

/** Make the key file when there is none; with exactly one already there, change nothing. */
export async function initKey(publicDir, { makeKey = () => randomBytes(16).toString('hex') } = {}) {
  await mkdir(publicDir, { recursive: true });
  const keys = await findKeys(publicDir);
  if (keys.length > 1) {
    throw new Error(`expected at most one IndexNow key file in ${publicDir}, found ${keys.length}`);
  }
  if (keys.length === 1) return { key: keys[0], created: false };
  const key = makeKey();
  // `wx` so that two runs at once cannot both write: the second fails instead of overwriting.
  await writeFile(join(publicDir, `${key}.txt`), key, { flag: 'wx' });
  return { key, created: true };
}

const XML_ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" };

function decodeXml(text) {
  return text.replace(/&(?:amp|lt|gt|quot|apos);/g, (entity) => XML_ENTITIES[entity]);
}

/** Each <url> of a sitemap, with its lastmod or null. */
export function parseSitemap(xml) {
  const entries = [];
  for (const [, block] of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = /<loc>\s*([^<]+?)\s*<\/loc>/.exec(block)?.[1];
    if (!loc) continue;
    const lastmod = /<lastmod>\s*([^<]+?)\s*<\/lastmod>/.exec(block)?.[1] ?? null;
    entries.push({ url: decodeXml(loc), lastmod });
  }
  return entries;
}

/** The files a sitemap index points at, or [] for a plain sitemap. */
export function parseSitemapIndex(xml) {
  if (!/<sitemapindex[\s>]/.test(xml)) return [];
  return [...xml.matchAll(/<sitemap>[\s\S]*?<loc>\s*([^<]+?)\s*<\/loc>[\s\S]*?<\/sitemap>/g)].map(
    (m) => decodeXml(m[1])
  );
}

/**
 * Every <url> behind a sitemap, following an index one level down.
 *
 * The index names its files at the public address; they are read from the same origin as the
 * index instead (the web app on loopback during a deploy), so a deploy never waits on DNS, TLS
 * or nginx to list its own pages.
 */
export async function readSitemap(sitemapUrl, fetchImpl = fetch) {
  const text = async (url) => {
    const res = await fetchImpl(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    if (!res.ok) throw new Error(`sitemap answered ${res.status} at ${url}`);
    return res.text();
  };
  const xml = await text(sitemapUrl);
  const files = parseSitemapIndex(xml);
  if (files.length === 0) return parseSitemap(xml);
  const origin = new URL(sitemapUrl).origin;
  const entries = [];
  for (const file of files) {
    const { pathname, search } = new URL(file);
    entries.push(...parseSitemap(await text(`${origin}${pathname}${search}`)));
  }
  return entries;
}

/** Only the URLs of this site: IndexNow rejects a host that does not own the key. */
export function ofSite(entries, siteUrl) {
  if (!siteUrl) return entries;
  const origin = new URL(siteUrl).origin;
  return entries.filter(({ url }) => {
    try {
      return new URL(url).origin === origin;
    } catch {
      return false;
    }
  });
}

/** What to submit: new URLs, and known ones whose lastmod moved. */
export function changed(entries, sent) {
  return entries.filter(({ url, lastmod }) => !(url in sent) || sent[url] !== lastmod);
}

/**
 * One request per batch of up to 10,000 URLs; resolves to the URLs accepted.
 *
 * `onBatch(urlList)` is awaited after each accepted batch, so a caller can remember what went
 * through before a later batch fails and throws.
 */
export async function submit(urls, { key, fetchImpl = fetch, onBatch }) {
  if (urls.length === 0) return [];
  const host = new URL(urls[0]).host;
  const keyLocation = `https://${host}/${key}.txt`;
  const accepted = [];
  for (let i = 0; i < urls.length; i += BATCH) {
    const urlList = urls.slice(i, i + BATCH);
    const res = await fetchImpl(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ host, key, keyLocation, urlList }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    // 200 and 202 both mean received; anything else stops here, so the rest are retried on the
    // next run.
    if (res.status !== 200 && res.status !== 202) {
      throw new Error(`IndexNow answered ${res.status} for ${urlList.length} URL(s)`);
    }
    accepted.push(...urlList);
    await onBatch?.(urlList);
  }
  return accepted;
}

async function readState(path) {
  try {
    return JSON.parse(await readFile(path, 'utf8'));
  } catch {
    return {};
  }
}

/** The state belongs to the machine, not to a release: a deploy replaces the release folder. */
export function assertOutsideRelease(statePath, root = ROOT) {
  const from = relative(resolve(root), resolve(statePath));
  const outside = from === '..' || from.startsWith(`..${sep}`) || isAbsolute(from);
  if (!outside) {
    throw new Error(`INDEXNOW_STATE must be outside the release folder ${root}, not ${statePath}`);
  }
}

export async function run({
  siteUrl = '',
  force = false,
  sitemapUrl = 'http://127.0.0.1:3000/sitemap.xml',
  statePath = join(homedir(), '.local', 'state', 'tabsira', 'indexnow.json'),
  publicDir = join(ROOT, 'apps', 'web', 'public'),
  root = ROOT,
  dryRun = false,
  fetchImpl = fetch,
  log = console.log,
} = {}) {
  const site = siteUrl.replace(/\/+$/, '');
  if (!force && site !== PRODUCTION_SITE) {
    throw new Error(
      `refusing to run: SITE_URL is ${site || 'not set'}, not ${PRODUCTION_SITE} (--force overrides)`
    );
  }
  assertOutsideRelease(statePath, root);
  const key = await findKey(publicDir);
  const entries = ofSite(await readSitemap(sitemapUrl, fetchImpl), site);
  const sent = await readState(statePath);
  const todo = changed(entries, sent);
  log(`[indexnow] ${entries.length} URL(s) in the sitemap, ${todo.length} new or changed`);
  if (dryRun || todo.length === 0) return todo.length;

  const lastmods = new Map(todo.map((e) => [e.url, e.lastmod]));
  await mkdir(dirname(statePath), { recursive: true });
  // Each accepted batch is written down at once: if a later one is refused, the next run sends
  // only what is left instead of everything again.
  const accepted = await submit([...lastmods.keys()], {
    key,
    fetchImpl,
    onBatch: async (urlList) => {
      for (const url of urlList) sent[url] = lastmods.get(url);
      await writeFile(statePath, JSON.stringify(sent));
    },
  });
  log(`[indexnow] submitted ${accepted.length} URL(s)`);
  return accepted.length;
}

/**
 * The command line. Returns the exit code: 0 whatever happens to the submission, since a deploy
 * must not fail for it; 1 only when `--init` cannot make the key file, which is a setup error.
 */
export async function main(
  argv,
  env,
  {
    fetchImpl = fetch,
    log = console.log,
    warn = console.warn,
    publicDir = join(ROOT, 'apps', 'web', 'public'),
  } = {}
) {
  if (argv.includes('--init')) {
    try {
      const { key, created } = await initKey(publicDir);
      log(`[indexnow] ${created ? 'created' : 'found'} apps/web/public/${key}.txt`);
      return 0;
    } catch (error) {
      warn(`[indexnow] cannot make the key file: ${error.message}`);
      return 1;
    }
  }
  try {
    await run({
      siteUrl: env.SITE_URL ?? '',
      force: argv.includes('--force'),
      dryRun: argv.includes('--dry-run'),
      ...(env.SITEMAP_URL ? { sitemapUrl: env.SITEMAP_URL } : {}),
      ...(env.INDEXNOW_STATE ? { statePath: env.INDEXNOW_STATE } : {}),
      publicDir,
      fetchImpl,
      log,
    });
  } catch (error) {
    // Never a failed deploy: the site is live, the sitemap says the same.
    warn(`[indexnow] not submitted: ${error.message}`);
  }
  return 0;
}

/* node:coverage ignore next 3 */
if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  process.exitCode = await main(process.argv.slice(2), process.env);
}
