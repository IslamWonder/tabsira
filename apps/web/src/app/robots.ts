import type { MetadataRoute } from 'next';
import { AI_AGENTS } from '@/lib/crawlers';
import { absoluteUrl, PRIVATE_PATHS } from '@/lib/seo';

/**
 * Everyone, and every AI agent named one by one (docs/SEO.md §1), may read the
 * public pages; private areas are closed to all of them. Only the sitemap
 * index is named, never its children, and there is no `Host:` line.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: ['*', ...AI_AGENTS], allow: '/', disallow: [...PRIVATE_PATHS] }],
    sitemap: absoluteUrl('/sitemap.xml'),
  };
}
