import type { Metadata } from 'next';
import { PostScreen } from '@/components/community/post-screen';
import { JsonLd } from '@/components/legal/json-ld';
import { featureEnabled } from '@/config/server-env';
import { articleJsonLd, pageMetadata } from '@/lib/seo';
import { messages } from '@/messages';
import { postPath } from '@/social/identity';
import { postOnServer } from '@/social/server';

export const dynamic = 'force-dynamic';

type Params = { params: Promise<{ id: string }> };

const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

/**
 * A public post is indexable (docs/SEO.md: `article`, with the author's public
 * name only). The metadata comes from what a stranger may read: a post that is
 * not public, gone, or unreachable right now carries `noindex` and the generic
 * title, so nothing private and nothing stale is ever advertised.
 */
export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const path = postPath(id);
  const result = PUBLIC_ID.test(id) ? await postOnServer(id) : null;
  if (!result?.ok) {
    return pageMetadata({
      path,
      title: messages.community.title,
      description: messages.community.lead,
      noindex: true,
    });
  }
  const post = result.data;
  return pageMetadata({
    path,
    title: post.insight.title,
    description: post.insight.glimpse,
    type: 'article',
  });
}

export default async function PostPage({ params }: Readonly<Params>) {
  const { id } = await params;
  const result = PUBLIC_ID.test(id) ? await postOnServer(id) : null;
  return (
    <>
      {result?.ok && result.data.published_at !== null ? (
        <JsonLd
          data={articleJsonLd({
            path: postPath(id),
            headline: result.data.insight.title,
            datePublished: result.data.published_at,
            authorName: result.data.author.public_name ?? undefined,
          })}
        />
      ) : null}
      <PostScreen postId={id} comments={featureEnabled('social_comments')} />
    </>
  );
}
