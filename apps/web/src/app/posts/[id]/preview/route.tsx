import { NOT_FOUND, previewLoad, previewResponse } from '@/lib/share-card/preview-response';
import { postOnServer } from '@/social/server';

/*
 * The link preview image of a public post (og:image), drawn like an insight's:
 * the published photo, if any, the insight's title and glimpse, the mark. The
 * post is read as a stranger reads it; one shown to followers only, or not
 * published, has no preview.
 */

const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context) {
  const { id } = await params;
  if (!PUBLIC_ID.test(id)) {
    return previewResponse(NOT_FOUND);
  }
  return previewResponse(
    previewLoad(await postOnServer(id), (post) =>
      post.status === 'published' && post.visibility === 'public' ? post.insight : null
    )
  );
}
