import { sitemapIndexResponse } from '@/sitemap/server';

// Read at request time: the address comes from SITE_URL and the lists from the API.
export const dynamic = 'force-dynamic';

export function GET(): Promise<Response> {
  return sitemapIndexResponse();
}
