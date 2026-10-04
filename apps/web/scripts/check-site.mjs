// Site checks over HTTP (docs/SEO.md §7), ported from
// the reference site/scripts/check-site.mjs. Start the server first:
//
//   BASE_URL=http://127.0.0.1:3000 pnpm --filter @tabsira/web check:site
//
// Every indexed route must answer 200 with a title, a description and a
// canonical; the Consent Mode defaults, when there are any, must come before
// any Google script and no Google or Clarity script may be in the HTML at all
// (they are injected after consent); an unknown path is a real 404; and no
// internal link of the public pages is dead.

import { baseUrl, fetchPage, report } from './lib/html.mjs';
import { INDEXED_ROUTES } from './lib/site-routes.mjs';

const problems = [];
const fail = (where, message) => problems.push(`${where}: ${message}`);
const links = new Set();

function checkConsentOrder(where, html) {
  const defaultsAt = html.indexOf("gtag('consent','default'");
  if (defaultsAt === -1 && html.includes('consent-mode-defaults')) {
    fail(where, 'the Consent Mode defaults script has no default call');
  }
  if (/googletagmanager\.com|google-analytics\.com|clarity\.ms/.test(html)) {
    fail(where, 'a Google or Clarity address is in the HTML before any consent');
  }
  if (defaultsAt !== -1 && !/analytics_storage:'denied'/.test(html)) {
    fail(where, 'the Consent Mode defaults do not deny analytics storage');
  }
}

for (const route of INDEXED_ROUTES) {
  const page = await fetchPage(route);
  if (page.text === null) {
    fail(route, `HTTP ${page.status}`);
    continue;
  }
  const html = page.text;
  if (!/<title>[^<]+<\/title>/.test(html)) {
    fail(route, 'no title');
  }
  if (!/name="description" content="[^"]+"/.test(html)) {
    fail(route, 'no description');
  }
  if (!/rel="canonical" href="[^"]+"/.test(html)) {
    fail(route, 'no canonical');
  }
  checkConsentOrder(route, html);
  for (const [, href] of html.matchAll(/href="(\/[^"#?]*)"/g)) {
    if (!href.startsWith('/_next') && !href.includes('.')) {
      links.add(href);
    }
  }
}

const missing = await fetchPage('/this-page-does-not-exist-check-site');
if (missing.status !== 404) {
  fail('/this-page-does-not-exist-check-site', `answered ${missing.status}, want a real 404`);
}

for (const href of links) {
  const response = await fetch(`${baseUrl()}${href}`, { method: 'HEAD', redirect: 'manual' });
  // A redirect is a live link; only a missing or broken page is a problem.
  if (response.status >= 400) {
    fail('link', `${href} -> HTTP ${response.status}`);
  }
}

report(problems, `checked ${INDEXED_ROUTES.length} pages and ${links.size} internal links`);
