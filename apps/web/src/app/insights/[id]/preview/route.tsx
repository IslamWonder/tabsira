import { loadPublicInsight } from '@/lib/share-card/load';
import { previewResponse } from '@/lib/share-card/preview-response';

/*
 * The link preview image of a published insight (og:image): 1200 x 630 with
 * the published photo, if any, the title and the glimpse.
 */

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context) {
  const { id } = await params;
  const loaded = await loadPublicInsight(id);
  return previewResponse(
    loaded.kind === 'insight' ? { kind: 'subject', subject: loaded.insight } : loaded
  );
}
