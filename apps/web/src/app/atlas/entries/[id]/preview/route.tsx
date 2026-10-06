import { entryOnServer } from '@/atlas/server';
import { NOT_FOUND, previewLoad, previewResponse } from '@/lib/share-card/preview-response';

/*
 * The link preview image of a published map entry (og:image), drawn like an
 * insight's: the photo its owner chose to show, if any, the title, the glimpse
 * and the mark. Never the place: the preview adds nothing the page does not show.
 */

const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context) {
  const { id } = await params;
  if (!PUBLIC_ID.test(id)) {
    return previewResponse(NOT_FOUND);
  }
  return previewResponse(previewLoad(await entryOnServer(id), (entry) => entry));
}
