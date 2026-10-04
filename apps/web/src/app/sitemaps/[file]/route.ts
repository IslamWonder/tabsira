import { sitemapChildResponse } from '@/sitemap/server';

export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ file: string }> }
): Promise<Response> {
  return sitemapChildResponse((await params).file);
}
