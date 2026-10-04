import type { Metadata } from 'next';
import { siteOrigin } from '@/lib/site';

/** The public legal routes; the sitemap's static list must carry all three. */
export const LEGAL_PATHS = ['/terms', '/privacy', '/support'] as const;
export type LegalPath = (typeof LEGAL_PATHS)[number];

export interface LegalPageSeo {
  path: LegalPath;
  title: string;
  description: string;
}

/**
 * Indexed, self-canonical, and shown without a snippet: a legal text must be
 * read whole, never quoted in part by a search result (docs/SEO.md §1).
 */
export function legalMetadata({ path, title, description }: LegalPageSeo): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path, languages: { ar: path, 'x-default': path } },
    robots: { index: true, follow: true, 'max-snippet': 0 },
    openGraph: { type: 'website', locale: 'ar', title, description, url: path },
    twitter: { card: 'summary_large_image', title, description },
  };
}

/** schema.org WebPage for one legal page; every field is printed on the page itself. */
export function webPageJsonLd(
  { path, title, description }: LegalPageSeo,
  dateModified?: string
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: title,
    description,
    url: new URL(path, siteOrigin()).toString(),
    inLanguage: 'ar',
    ...(dateModified === undefined ? {} : { dateModified }),
  };
}
