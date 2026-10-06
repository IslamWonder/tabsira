// SEO and machine-readability audit (docs/SEO.md §7) for one language and the
// routes of TABSIRA. It reads a running server:
//
//   BASE_URL=http://127.0.0.1:3000 SITE_URL=https://tabsira.me pnpm --filter @tabsira/web check:seo
//
// SITE_URL is the origin the build was made for (default https://tabsira.me):
// every canonical, og:url and JSON-LD address must carry it, so a build that
// leaked localhost or a .test host fails here.

import { attr, baseUrl, decodeEntities, fetchPage, GLUE, jsonLd, report } from './lib/html.mjs';
import {
  AI_AGENTS,
  INDEXED_ROUTES,
  MANIFEST_ICON_SIZES,
  PRIVATE_PATHS,
  PRODUCTION_ORIGIN,
  UNLISTED_ROUTES,
} from './lib/site-routes.mjs';

const ORIGIN = (process.env.SITE_URL ?? PRODUCTION_ORIGIN).replace(/\/$/, '');
const problems = [];
const note = (where, message) => problems.push(`${where}: ${message}`);

/** What the canonical of a route must be: the origin and the path; the home page is the origin itself, as Next writes it. */
const expectedUrl = (route) => (route === '/' ? ORIGIN : `${ORIGIN}${route}`);

function checkIndexed(route, html) {
  const where = route;
  const title = decodeEntities(attr(html, /<title>([^<]*)<\/title>/));
  if (!title) {
    note(where, 'no <title>');
  } else if (title.length > 65) {
    note(where, `title ${title.length} characters (over 65)`);
  }
  const description = decodeEntities(attr(html, /name="description" content="([^"]*)"/));
  if (!description) {
    note(where, 'no meta description');
  } else if (description.length > 165) {
    note(where, `description ${description.length} characters (over 165)`);
  }

  const canonical = attr(html, /rel="canonical" href="([^"]+)"/);
  if (canonical !== expectedUrl(route)) {
    note(where, `canonical is ${canonical}, expected ${expectedUrl(route)}`);
  }
  for (const language of ['ar', 'x-default']) {
    const alternate = attr(html, new RegExp(`hreflang="${language}" href="([^"]+)"`, 'i'));
    if (alternate !== expectedUrl(route)) {
      note(where, `hreflang ${language} is ${alternate}, expected ${expectedUrl(route)}`);
    }
  }
  const ogUrl = attr(html, /property="og:url" content="([^"]+)"/);
  if (ogUrl !== expectedUrl(route)) {
    note(where, `og:url is ${ogUrl}, expected ${expectedUrl(route)}`);
  }
  for (const property of ['og:title', 'og:description', 'og:image', 'og:type', 'og:locale']) {
    if (!html.includes(`property="${property}"`)) {
      note(where, `no ${property}`);
    }
  }
  if (attr(html, /property="og:locale" content="([^"]+)"/) !== 'ar_AR') {
    note(where, 'og:locale is not ar_AR');
  }
  for (const name of ['twitter:card', 'twitter:image']) {
    if (!html.includes(`name="${name}"`)) {
      note(where, `no ${name}`);
    }
  }
  if (/name="robots"[^>]*noindex/.test(html)) {
    note(where, 'noindex on an indexable page');
  }
  if (!/<html[^>]*\blang="ar"/.test(html) || !/<html[^>]*\bdir="rtl"/.test(html)) {
    note(where, '<html> is not lang="ar" dir="rtl"');
  }
  if (!html.includes('id="main"')) {
    note(where, 'no #main landmark');
  }
  const headings = [...html.matchAll(/<h1[\s>]/g)].length;
  if (headings !== 1) {
    note(where, `${headings} <h1> elements (want exactly 1)`);
  }
  for (const [tag] of html.matchAll(/<img[^>]*>/g)) {
    if (!/\salt=/.test(tag)) {
      note(where, `img without alt: ${tag.slice(0, 70)}`);
    }
  }
  for (const [, before, tag, next, after] of html.matchAll(GLUE)) {
    note(where, `"${before}${after}" welded across <${tag}>/<${next}>`);
  }
  if (ORIGIN === PRODUCTION_ORIGIN && /localhost|127\.0\.0\.1|\.test\b/.test(canonical ?? '')) {
    note(where, 'the build leaks a local address');
  }
  checkStructuredData(route, html);
}

function checkStructuredData(route, html) {
  const where = route;
  const { parsed, invalid } = jsonLd(html);
  if (invalid > 0) {
    note(where, `${invalid} invalid JSON-LD block(s)`);
  }
  const types = parsed.map((block) => block['@type']);
  const wanted = route === '/' ? ['Organization', 'WebSite'] : ['WebPage', 'BreadcrumbList'];
  for (const type of wanted) {
    if (!types.includes(type)) {
      note(where, `no ${type} JSON-LD`);
    }
  }
  for (const block of parsed) {
    const url = block.url ?? block.logo?.url;
    if (
      typeof url === 'string' &&
      url.replace(/\/$/, '') !== ORIGIN &&
      !url.startsWith(`${ORIGIN}/`)
    ) {
      note(where, `JSON-LD address ${url} is not under ${ORIGIN}`);
    }
  }
}

function checkUnlisted(route, page) {
  if (page.status === 404) {
    note(route, 'unlisted route answered 404');
    return;
  }
  if (page.text !== null && !/name="robots"[^>]*noindex/.test(page.text)) {
    note(route, 'unlisted route without noindex');
  }
}

async function checkRobots() {
  const { text } = await fetchPage('/robots.txt');
  if (text === null) {
    note('/robots.txt', 'missing');
    return;
  }
  const sitemaps = [...text.matchAll(/^Sitemap:\s*(\S+)/gim)].map((match) => match[1]);
  if (sitemaps.length !== 1 || sitemaps[0] !== `${ORIGIN}/sitemap.xml`) {
    note('/robots.txt', `Sitemap lines are ${JSON.stringify(sitemaps)}, want only the index`);
  }
  if (/^Host:/im.test(text)) {
    note('/robots.txt', 'has a Host: line');
  }
  for (const agent of AI_AGENTS) {
    if (!new RegExp(String.raw`^User-Agent:\s*${agent}\s*$`, 'im').test(text)) {
      note('/robots.txt', `${agent} not named`);
    }
  }
  for (const path of PRIVATE_PATHS) {
    if (!text.includes(`Disallow: ${path}`)) {
      note('/robots.txt', `${path} not disallowed`);
    }
  }
}

async function checkAssets() {
  const llms = await fetchPage('/llms.txt');
  if (llms.text === null || !llms.text.startsWith('# ')) {
    note('/llms.txt', 'missing or not a heading first');
  }
  if ((await fetchPage('/llms-full.txt')).text === null) {
    note('/llms-full.txt', 'missing');
  }
  const manifest = await fetchPage('/manifest.webmanifest');
  if (manifest.text === null) {
    note('/manifest.webmanifest', 'missing');
  } else {
    if (!(manifest.headers.get('content-type') ?? '').includes('manifest+json')) {
      note('/manifest.webmanifest', `served as ${manifest.headers.get('content-type')}`);
    }
    const sizes = new Set(JSON.parse(manifest.text).icons.map((icon) => icon.sizes));
    for (const size of MANIFEST_ICON_SIZES) {
      if (!sizes.has(size)) {
        note('/manifest.webmanifest', `no icon declared at ${size}`);
      }
    }
  }
  for (const file of [
    '/favicon.ico',
    '/icons/apple-icon.png',
    '/icons/icon-192.png',
    '/icons/icon-512.png',
    '/icons/maskable-512.png',
    '/icons/mstile-150.png',
    '/browserconfig.xml',
    '/share/default.jpg',
  ]) {
    const response = await fetch(`${baseUrl()}${file}`, { method: 'HEAD' });
    if (!response.ok) {
      note(file, `HTTP ${response.status}`);
    }
  }
}

let pages = 0;
for (const route of INDEXED_ROUTES) {
  const page = await fetchPage(route);
  if (page.text === null) {
    note(route, `HTTP ${page.status}`);
    continue;
  }
  pages += 1;
  checkIndexed(route, page.text);
}
for (const route of UNLISTED_ROUTES) {
  checkUnlisted(route, await fetchPage(route));
}
await checkRobots();
await checkAssets();

report(problems, `audited ${pages} indexed pages and ${UNLISTED_ROUTES.length} unlisted routes`);
