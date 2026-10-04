// Tests of scripts/indexnow.mjs with node's own runner: node --test scripts/
// No network: every request goes to a function that records it.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  assertOutsideRelease,
  BATCH,
  changed,
  ENDPOINT,
  findKey,
  findKeys,
  initKey,
  main,
  ofSite,
  PRODUCTION_SITE,
  parseSitemap,
  parseSitemapIndex,
  readSitemap,
  run,
  submit,
} from './indexnow.mjs';

const SCRIPT = fileURLToPath(new URL('./indexnow.mjs', import.meta.url));
// A made-up key, built so no secret scanner mistakes it for one.
const KEY = 'ab'.repeat(16);
const SITE = PRODUCTION_SITE;
const dirs = [];

async function tmp() {
  const dir = await mkdtemp(join(tmpdir(), 'tabsira-indexnow-'));
  dirs.push(dir);
  return dir;
}

async function publicDir(files = { [`${KEY}.txt`]: KEY }) {
  const dir = await tmp();
  for (const [name, body] of Object.entries(files)) await writeFile(join(dir, name), body);
  return dir;
}

after(async () => {
  for (const dir of dirs) await rm(dir, { recursive: true, force: true });
});

const SITEMAP = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>${SITE}/</loc></url>
<url><loc>${SITE}/about</loc><lastmod>2026-10-04T00:00:00.000Z</lastmod></url>
<url><changefreq>daily</changefreq></url>
</urlset>`;

/** A fetch that serves the given files and records every call. */
function server(files, { indexNow = 200 } = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url, init });
    if (url === ENDPOINT) return { status: typeof indexNow === 'function' ? indexNow() : indexNow };
    if (url in files) return { ok: true, status: 200, text: async () => files[url] };
    return { ok: false, status: 404 };
  };
  fetchImpl.calls = calls;
  fetchImpl.posts = () =>
    calls.filter((c) => c.url === ENDPOINT).map((c) => JSON.parse(c.init.body));
  return fetchImpl;
}

const SITEMAP_URL = 'http://127.0.0.1:3000/sitemap.xml';

describe('the key file', () => {
  it('is the one public file named after its own contents, and nothing else', async () => {
    const dir = await publicDir({
      [`${KEY}.txt`]: `${KEY}\n`,
      'robots.txt': 'User-agent: *',
      'deadbeefdead.txt': 'something else',
      'short.txt': 'short',
    });

    assert.deepEqual(await findKeys(dir), [KEY]);
    assert.equal(await findKey(dir), KEY);
  });

  it('is an error when there is none or there are two', async () => {
    await assert.rejects(findKey(await publicDir({})), /found 0/);
    const other = 'cd'.repeat(16);
    await assert.rejects(
      findKey(await publicDir({ [`${KEY}.txt`]: KEY, [`${other}.txt`]: other })),
      /found 2/
    );
  });

  it('is made by --init when missing: 32 hex digits, file name equal to its contents', async () => {
    const dir = join(await tmp(), 'apps', 'web', 'public');

    const made = await initKey(dir);

    assert.equal(made.created, true);
    assert.match(made.key, /^[0-9a-f]{32}$/);
    assert.deepEqual(await readdir(dir), [`${made.key}.txt`]);
    assert.equal(await readFile(join(dir, `${made.key}.txt`), 'utf8'), made.key);
  });

  it('is left alone by a second --init', async () => {
    const dir = await tmp();
    const first = await initKey(dir);

    const second = await initKey(dir);

    assert.deepEqual(second, { key: first.key, created: false });
    assert.equal((await readdir(dir)).length, 1);
  });

  it('is never replaced when two already exist, and --init says so', async () => {
    const other = 'cd'.repeat(16);
    const dir = await publicDir({ [`${KEY}.txt`]: KEY, [`${other}.txt`]: other });

    await assert.rejects(initKey(dir), /at most one IndexNow key file/);
    assert.equal((await readdir(dir)).length, 2);
  });

  it('is never overwritten by a second run at the same moment', async () => {
    const dir = await publicDir({ 'abcdefgh.txt': 'not its own name' });

    await assert.rejects(initKey(dir, { makeKey: () => 'abcdefgh' }), /EEXIST/);
    assert.equal(await readFile(join(dir, 'abcdefgh.txt'), 'utf8'), 'not its own name');
  });
});

describe('reading the sitemap', () => {
  it('lists each URL with its lastmod, or null, and decodes XML entities', () => {
    const xml = `<urlset><url><loc>${SITE}/a?x=1&amp;y=2</loc></url>${SITEMAP.slice(SITEMAP.indexOf('<url>'))}`;

    assert.deepEqual(parseSitemap(xml), [
      { url: `${SITE}/a?x=1&y=2`, lastmod: null },
      { url: `${SITE}/`, lastmod: null },
      { url: `${SITE}/about`, lastmod: '2026-10-04T00:00:00.000Z' },
    ]);
  });

  it('names the files of an index, and none for a plain sitemap', () => {
    const index = `<sitemapindex><sitemap><loc>${SITE}/sitemaps/static-0.xml</loc></sitemap>
<sitemap><loc>${SITE}/sitemaps/posts-0.xml?a=1&amp;b=2</loc><lastmod>2026-10-04</lastmod></sitemap></sitemapindex>`;

    assert.deepEqual(parseSitemapIndex(index), [
      `${SITE}/sitemaps/static-0.xml`,
      `${SITE}/sitemaps/posts-0.xml?a=1&b=2`,
    ]);
    assert.deepEqual(parseSitemapIndex(SITEMAP), []);
  });

  it('reads a plain sitemap as it is', async () => {
    const entries = await readSitemap(SITEMAP_URL, server({ [SITEMAP_URL]: SITEMAP }));

    assert.equal(entries.length, 2);
  });

  it('follows an index to its files, read from the origin of the index', async () => {
    const index = `<sitemapindex><sitemap><loc>${SITE}/sitemaps/static-0.xml</loc></sitemap>
<sitemap><loc>${SITE}/sitemaps/posts-0.xml</loc></sitemap></sitemapindex>`;
    const posts = `<urlset><url><loc>${SITE}/posts/1</loc><lastmod>2026-10-02</lastmod></url></urlset>`;
    const fetchImpl = server({
      [SITEMAP_URL]: index,
      'http://127.0.0.1:3000/sitemaps/static-0.xml': SITEMAP,
      'http://127.0.0.1:3000/sitemaps/posts-0.xml': posts,
    });

    const entries = await readSitemap(SITEMAP_URL, fetchImpl);

    assert.deepEqual(
      entries.map((e) => e.url),
      [`${SITE}/`, `${SITE}/about`, `${SITE}/posts/1`]
    );
    // Every request has a time limit, so a deploy never hangs.
    assert.ok(fetchImpl.calls.every((c) => c.init.signal instanceof AbortSignal));
  });

  it('is an error when the sitemap or one of its files does not answer', async () => {
    await assert.rejects(readSitemap(SITEMAP_URL, server({})), /sitemap answered 404 at/);
    const index = `<sitemapindex><sitemap><loc>${SITE}/sitemaps/x.xml</loc></sitemap></sitemapindex>`;
    await assert.rejects(
      readSitemap(SITEMAP_URL, server({ [SITEMAP_URL]: index })),
      /answered 404 at http:\/\/127.0.0.1:3000\/sitemaps\/x.xml/
    );
  });
});

describe('choosing what to send', () => {
  it('keeps only the URLs of this site', () => {
    const entries = [
      { url: `${SITE}/a`, lastmod: null },
      { url: 'https://other.example/b', lastmod: null },
      { url: 'http://tabsira.me/c', lastmod: null },
      { url: 'not a url', lastmod: null },
    ];

    assert.deepEqual(ofSite(entries, SITE), [entries[0]]);
    assert.equal(ofSite(entries, '').length, 4);
  });

  it('sends what is new or moved, never what was sent as it is', () => {
    const entries = parseSitemap(SITEMAP);
    assert.equal(changed(entries, {}).length, 2);
    const sent = { [`${SITE}/`]: null, [`${SITE}/about`]: '2026-10-04T00:00:00.000Z' };

    assert.deepEqual(changed(entries, sent), []);
    assert.deepEqual(changed(entries, { ...sent, [`${SITE}/about`]: '2026-09-01' }), [entries[1]]);
  });
});

describe('submitting', () => {
  const urls = (n) => Array.from({ length: n }, (_, i) => `${SITE}/posts/${i}`);

  it('posts the host, the key and where the key is, in batches of 10,000', async () => {
    const fetchImpl = server({});

    const accepted = await submit(urls(BATCH + 1), { key: KEY, fetchImpl });

    assert.equal(BATCH, 10000);
    assert.equal(accepted.length, BATCH + 1);
    const posts = fetchImpl.posts();
    assert.equal(posts.length, 2);
    assert.deepEqual([posts[0].urlList.length, posts[1].urlList.length], [BATCH, 1]);
    assert.equal(posts[0].host, 'tabsira.me');
    assert.equal(posts[0].key, KEY);
    assert.equal(posts[0].keyLocation, `${SITE}/${KEY}.txt`);
    const [{ init }] = fetchImpl.calls;
    assert.equal(init.method, 'POST');
    assert.equal(init.headers['Content-Type'], 'application/json; charset=utf-8');
    assert.ok(init.signal instanceof AbortSignal);
  });

  it('takes 200 and 202 as received', async () => {
    for (const status of [200, 202]) {
      const accepted = await submit(urls(1), {
        key: KEY,
        fetchImpl: server({}, { indexNow: status }),
      });
      assert.equal(accepted.length, 1);
    }
  });

  it('stops at a refusal and says how many URLs were in the batch', async () => {
    const fetchImpl = server({}, { indexNow: 429 });

    await assert.rejects(
      submit(urls(BATCH + 1), { key: KEY, fetchImpl }),
      /IndexNow answered 429 for 10000 URL\(s\)/
    );
    assert.equal(fetchImpl.posts().length, 1);
  });

  it('sends nothing when there is nothing to send', async () => {
    const fetchImpl = server({});

    assert.deepEqual(await submit([], { key: KEY, fetchImpl }), []);
    assert.equal(fetchImpl.calls.length, 0);
  });

  it('tells the caller after each accepted batch', async () => {
    const seen = [];

    await submit(urls(BATCH + 1), {
      key: KEY,
      fetchImpl: server({}),
      onBatch: (list) => seen.push(list.length),
    });

    assert.deepEqual(seen, [BATCH, 1]);
  });
});

describe('the state file', () => {
  it('must be outside the release folder', () => {
    const root = '/srv/tabsira/releases/42';

    assert.throws(() => assertOutsideRelease(`${root}/indexnow.json`, root), /outside the release/);
    assert.throws(
      () => assertOutsideRelease(`${root}/a/b/state.json`, root),
      /outside the release/
    );
    assert.throws(() => assertOutsideRelease(root, root), /outside the release/);
    assert.doesNotThrow(() => assertOutsideRelease('/var/lib/tabsira/indexnow.json', root));
    assert.doesNotThrow(() => assertOutsideRelease('/srv/tabsira/releases/42b/state.json', root));
    assert.doesNotThrow(() => assertOutsideRelease(`${root}/../shared/state.json`, root));
    assert.doesNotThrow(() => assertOutsideRelease(`${root}/..hidden/../../state.json`, root));
  });
});

describe('a run', () => {
  async function setup(extra = {}) {
    const dir = await tmp();
    return {
      siteUrl: SITE,
      sitemapUrl: SITEMAP_URL,
      statePath: join(dir, 'state', 'indexnow.json'),
      publicDir: await publicDir(),
      log: () => undefined,
      ...extra,
    };
  }

  it('submits once, remembers what it sent, and then has nothing to send', async () => {
    const options = await setup();
    const fetchImpl = server({ [SITEMAP_URL]: SITEMAP });

    assert.equal(await run({ ...options, fetchImpl }), 2);
    assert.deepEqual(fetchImpl.posts()[0].urlList, [`${SITE}/`, `${SITE}/about`]);
    assert.equal(await run({ ...options, fetchImpl }), 0);
    assert.equal(fetchImpl.posts().length, 1);
    assert.deepEqual(JSON.parse(await readFile(options.statePath, 'utf8')), {
      [`${SITE}/`]: null,
      [`${SITE}/about`]: '2026-10-04T00:00:00.000Z',
    });
  });

  it('sends a URL again when its lastmod has moved, and only that one', async () => {
    const options = await setup();
    await run({ ...options, fetchImpl: server({ [SITEMAP_URL]: SITEMAP }) });
    const moved = SITEMAP.replace('2026-10-04T00:00:00.000Z', '2026-10-05T08:00:00.000Z');
    const fetchImpl = server({ [SITEMAP_URL]: moved });

    assert.equal(await run({ ...options, fetchImpl }), 1);
    assert.deepEqual(fetchImpl.posts()[0].urlList, [`${SITE}/about`]);
  });

  it('writes nothing and sends nothing on a dry run', async () => {
    const options = await setup();
    const fetchImpl = server({ [SITEMAP_URL]: SITEMAP });

    assert.equal(await run({ ...options, fetchImpl, dryRun: true }), 2);
    assert.equal(fetchImpl.posts().length, 0);
    await assert.rejects(readFile(options.statePath, 'utf8'), /ENOENT/);
  });

  it('sends only the URLs of the site, whatever the sitemap lists', async () => {
    const options = await setup();
    const sitemap = `<urlset><url><loc>${SITE}/a</loc></url><url><loc>https://other.example/b</loc></url></urlset>`;
    const fetchImpl = server({ [SITEMAP_URL]: sitemap });

    assert.equal(await run({ ...options, fetchImpl }), 1);
    assert.deepEqual(fetchImpl.posts()[0].urlList, [`${SITE}/a`]);
  });

  it('remembers the batches that went through when a later one is refused', async () => {
    const options = await setup();
    const many = Array.from(
      { length: BATCH + 5 },
      (_, i) => `<url><loc>${SITE}/p/${i}</loc></url>`
    );
    let post = 0;
    const fetchImpl = server(
      { [SITEMAP_URL]: `<urlset>${many.join('')}</urlset>` },
      { indexNow: () => (++post === 1 ? 202 : 429) }
    );

    await assert.rejects(run({ ...options, fetchImpl }), /answered 429 for 5 URL/);

    const state = JSON.parse(await readFile(options.statePath, 'utf8'));
    assert.equal(Object.keys(state).length, BATCH);
    assert.ok(`${SITE}/p/0` in state && !(`${SITE}/p/${BATCH + 1}` in state));
  });

  it('refuses unless the site is the production one, or it is forced', async () => {
    const options = await setup();
    const fetchImpl = server({ [SITEMAP_URL]: SITEMAP });

    for (const siteUrl of [
      '',
      'https://staging.tabsira.me',
      'https://tabsira.test',
      'http://tabsira.me',
    ]) {
      await assert.rejects(run({ ...options, siteUrl, fetchImpl }), /refusing to run: SITE_URL is/);
    }
    assert.equal(fetchImpl.calls.length, 0);
    assert.equal(await run({ ...options, siteUrl: `${SITE}/`, fetchImpl }), 2);
  });

  it('can be forced for another site, and then sends that site only', async () => {
    const options = await setup();
    const sitemap = `<urlset><url><loc>https://staging.tabsira.me/a</loc></url><url><loc>${SITE}/b</loc></url></urlset>`;
    const fetchImpl = server({ [SITEMAP_URL]: sitemap });

    const sent = await run({
      ...options,
      siteUrl: 'https://staging.tabsira.me',
      force: true,
      fetchImpl,
    });

    assert.equal(sent, 1);
    assert.equal(fetchImpl.posts()[0].host, 'staging.tabsira.me');
  });

  it('refuses a state file inside the release folder', async () => {
    const options = await setup({ root: await tmp() });
    const state = join(options.root, 'indexnow.json');

    await assert.rejects(
      run({ ...options, statePath: state, fetchImpl: server({}) }),
      /INDEXNOW_STATE must be outside the release folder/
    );
  });

  it('fails when the sitemap does not answer or there is no key', async () => {
    const options = await setup();

    await assert.rejects(run({ ...options, fetchImpl: server({}) }), /sitemap answered 404/);
    await assert.rejects(
      run({ ...options, publicDir: await publicDir({}), fetchImpl: server({}) }),
      /found 0/
    );
  });

  it('starts again from nothing when the state file is missing or unreadable', async () => {
    const options = await setup();
    await run({ ...options, fetchImpl: server({ [SITEMAP_URL]: SITEMAP }) });
    await writeFile(options.statePath, '{ not json');

    assert.equal(await run({ ...options, fetchImpl: server({ [SITEMAP_URL]: SITEMAP }) }), 2);
  });
});

describe('the command line', () => {
  const quiet = () => {
    const lines = { log: [], warn: [] };
    return {
      lines,
      io: {
        log: (line) => lines.log.push(line),
        warn: (line) => lines.warn.push(line),
      },
    };
  };

  it('--init makes the key file once and then finds it', async () => {
    const dir = join(await tmp(), 'public');
    const { lines, io } = quiet();

    assert.equal(await main(['--init'], {}, { ...io, publicDir: dir }), 0);
    assert.equal(await main(['--init'], {}, { ...io, publicDir: dir }), 0);

    assert.match(lines.log[0], /^\[indexnow\] created apps\/web\/public\/[0-9a-f]{32}\.txt$/);
    assert.match(lines.log[1], /^\[indexnow\] found apps\/web\/public\/[0-9a-f]{32}\.txt$/);
    assert.equal((await readdir(dir)).length, 1);
  });

  it('--init exits 1, a setup error, when it cannot make the key file', async () => {
    const other = 'cd'.repeat(16);
    const dir = await publicDir({ [`${KEY}.txt`]: KEY, [`${other}.txt`]: other });
    const { lines, io } = quiet();

    assert.equal(await main(['--init'], {}, { ...io, publicDir: dir }), 1);
    assert.match(lines.warn[0], /cannot make the key file/);
  });

  it('warns and exits 0 when it is not production, and asks nobody anything', async () => {
    const { lines, io } = quiet();
    const fetchImpl = server({});

    for (const env of [{}, { SITE_URL: 'https://tabsira.test' }]) {
      assert.equal(await main([], env, { ...io, fetchImpl }), 0);
    }

    assert.equal(fetchImpl.calls.length, 0);
    assert.equal(lines.warn.length, 2);
    assert.match(
      lines.warn[0],
      /not submitted: refusing to run: SITE_URL is not set, not https:\/\/tabsira.me/
    );
  });

  it('submits in production, reading SITEMAP_URL and INDEXNOW_STATE from the environment', async () => {
    const dir = await tmp();
    const state = join(dir, 'indexnow.json');
    const keys = await publicDir();
    const { lines, io } = quiet();
    const fetchImpl = server({ 'http://127.0.0.1:4000/map.xml': SITEMAP });

    const code = await main(
      [],
      { SITE_URL: SITE, SITEMAP_URL: 'http://127.0.0.1:4000/map.xml', INDEXNOW_STATE: state },
      { ...io, fetchImpl, publicDir: keys }
    );

    assert.equal(code, 0);
    assert.deepEqual(lines.warn, []);
    assert.equal(fetchImpl.posts().length, 1);
    assert.equal(Object.keys(JSON.parse(await readFile(state, 'utf8'))).length, 2);
  });

  it('--dry-run reports and sends nothing; --force allows another site', async () => {
    const dir = await tmp();
    const env = { SITE_URL: 'https://staging.tabsira.me', INDEXNOW_STATE: join(dir, 's.json') };
    const keys = await publicDir();
    const { lines, io } = quiet();
    const fetchImpl = server({ [SITEMAP_URL]: SITEMAP });

    await main(['--force', '--dry-run'], env, { ...io, fetchImpl, publicDir: keys });

    assert.deepEqual(lines.warn, []);
    assert.match(lines.log[0], /0 URL\(s\) in the sitemap, 0 new or changed/);
    assert.equal(fetchImpl.posts().length, 0);
  });

  it('warns and exits 0 whatever goes wrong with the submission', async () => {
    const dir = await tmp();
    const { lines, io } = quiet();
    const env = { SITE_URL: SITE, INDEXNOW_STATE: join(dir, 's.json') };
    const keys = await publicDir();

    const down = await main([], env, { ...io, fetchImpl: server({}), publicDir: keys });
    const refused = await main([], env, {
      ...io,
      fetchImpl: server({ [SITEMAP_URL]: SITEMAP }, { indexNow: 403 }),
      publicDir: keys,
    });

    assert.deepEqual([down, refused], [0, 0]);
    assert.match(lines.warn[0], /not submitted: sitemap answered 404/);
    assert.match(lines.warn[1], /not submitted: IndexNow answered 403/);
  });

  it('runs as a program: a warning on stderr and exit code 0 when it must not submit', async () => {
    const result = spawnSync(process.execPath, [SCRIPT], {
      env: { PATH: process.env.PATH, SITE_URL: 'https://tabsira.test' },
      encoding: 'utf8',
    });

    assert.equal(result.status, 0);
    assert.match(result.stderr, /\[indexnow\] not submitted: refusing to run/);
  });

  it('runs as a program even when the sitemap is unreachable', async () => {
    const dir = await tmp();
    const result = spawnSync(process.execPath, [SCRIPT, '--force'], {
      env: {
        PATH: process.env.PATH,
        SITE_URL: SITE,
        SITEMAP_URL: 'http://127.0.0.1:9/sitemap.xml',
        INDEXNOW_STATE: join(dir, 's.json'),
      },
      encoding: 'utf8',
    });

    assert.equal(result.status, 0);
    assert.match(result.stderr, /\[indexnow\] not submitted/);
  });
});
