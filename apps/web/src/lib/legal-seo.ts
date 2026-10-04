import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export { webPageJsonLd } from '@/lib/seo';

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
export function legalMetadata(seo: LegalPageSeo): Metadata {
  return pageMetadata({ ...seo, noSnippet: true });
}
