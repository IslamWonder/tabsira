// Small helpers shared by check-seo.mjs and check-site.mjs: fetching a page and
// reading the few tags the checks look at. No dependency, no parser: the
// tags are the ones Next.js writes, in its own quoting.

const INLINE = 'span|a|b|i|em|strong|code|label|time|small|abbr|sup|sub';
// Two adjacent inline elements with no space between them weld two words in
// every text extractor (docs/SEO.md §1, text extraction).
export const GLUE = new RegExp(
  `([\\p{L}\\p{N},.;:!?)\\]"])</(${INLINE})><(${INLINE})\\b[^>]*>([\\p{L}\\p{N}("])`,
  'gu'
);

/** Titles and descriptions are measured as a reader sees them, not as escaped. */
export function decodeEntities(value) {
  if (!value) {
    return value;
  }
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;|&apos;|&#x27;/gi, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&amp;/g, '&');
}

export function baseUrl() {
  return (process.env.BASE_URL ?? 'http://127.0.0.1:3000').replace(/\/$/, '');
}

/** The page, or null when it did not answer 200. Redirects are not followed: a route is its own address. */
export async function fetchPage(pathname, init = {}) {
  const response = await fetch(`${baseUrl()}${pathname}`, { redirect: 'manual', ...init });
  return response.status === 200
    ? { text: await response.text(), headers: response.headers, status: 200 }
    : { text: null, headers: response.headers, status: response.status };
}

export function attr(html, pattern) {
  return html.match(pattern)?.[1];
}

/** Every JSON-LD block of a page, parsed; `invalid` counts the ones that did not parse. */
export function jsonLd(html) {
  const blocks = [...html.matchAll(/<script type="application\/ld\+json"[^>]*>(.*?)<\/script>/gs)];
  const parsed = [];
  let invalid = 0;
  for (const [, json] of blocks) {
    try {
      parsed.push(JSON.parse(json));
    } catch {
      invalid += 1;
    }
  }
  return { parsed, invalid };
}

export function report(problems, summary) {
  console.log(summary);
  if (problems.length > 0) {
    console.error(`\n${problems.length} problem(s):`);
    for (const problem of problems) {
      console.error(`  - ${problem}`);
    }
    process.exit(1);
  }
  console.log('all good');
}
