import type { components } from '@/lib/api/schema';

export type SitemapEntry = components['schemas']['SitemapEntry'];
export type SitemapIndex = components['schemas']['SitemapIndex'];

/*
 * Sitemap XML (sitemaps.org protocol), written by hand: the API says what is
 * listed (decision 29), this only spells it out. Every address is absolute,
 * built from the origin given, and every value is escaped.
 */

const PROLOG = '<?xml version="1.0" encoding="UTF-8"?>\n';

const ESCAPES: Readonly<Record<string, string>> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&apos;',
};

function escapeXml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ESCAPES[char] as string);
}

function tag(name: string, value: string): string {
  return `<${name}>${escapeXml(value)}</${name}>`;
}

/** The address of one child sitemap: `/sitemaps/<section>-<page>.xml`. */
export function childPath(section: string, page: number): string {
  return `/sitemaps/${section}-${page}.xml`;
}

/** The sitemap index: one `<sitemap>` per page of every section, in the API's order. */
export function indexXml(index: SitemapIndex, origin: URL): string {
  const items = Object.entries(index.sections).flatMap(([section, pages]) =>
    pages.map(({ page, lastmod }) => {
      const loc = tag('loc', new URL(childPath(section, page), origin).toString());
      return `<sitemap>${loc}${lastmod ? tag('lastmod', lastmod) : ''}</sitemap>`;
    })
  );
  return `${PROLOG}<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${items.join('')}</sitemapindex>\n`;
}

/** One page of one section as a `<urlset>`, with the pictures each page shows. */
export function urlsetXml(entries: readonly SitemapEntry[], origin: URL): string {
  const items = entries.map(({ path, lastmod, images }) => {
    const loc = tag('loc', new URL(path, origin).toString());
    const stamp = lastmod ? tag('lastmod', lastmod) : '';
    const pictures = (images ?? [])
      .map((image) => `<image:image>${tag('image:loc', image)}</image:image>`)
      .join('');
    return `<url>${loc}${stamp}${pictures}</url>`;
  });
  return `${PROLOG}<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">${items.join('')}</urlset>\n`;
}
