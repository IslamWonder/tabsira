import { adminInspectorUrl } from '@/config/server-env';

/*
 * The developer panel of v2 §23, `/dev/inspect/{scanId}`. Development only, like
 * /dev/ui: the `dev.ts` extension exists under `next dev` alone, so a production
 * build has no such route. It hands over to the scan inspector of the admin area
 * (apps/api/src/admin/views/inspector.py), where the admin session, the second
 * factor and the audit log already stand guard; nothing is rendered here, and
 * nothing is indexed.
 */

type Context = { params: Promise<{ scanId: string }> };

const HEADERS = { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  const { scanId } = await params;
  const target = adminInspectorUrl(scanId);
  if (target === null) {
    return new Response(null, { status: 404, headers: HEADERS });
  }
  return new Response(null, { status: 307, headers: { ...HEADERS, Location: target } });
}
