import type { Metadata } from 'next';
import { entryOnServer } from '@/atlas/server';
import { EntryScreen } from '@/components/atlas/entry-screen';
import { JsonLd } from '@/components/legal/json-ld';
import { articleJsonLd, pageMetadata } from '@/lib/seo';
import { messages } from '@/messages';

export const dynamic = 'force-dynamic';

type Params = { params: Promise<{ id: string }> };

const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;

function path(id: string): string {
  return `/atlas/entries/${id}`;
}

/**
 * A published entry is indexable with its title and glimpse (docs/SEO.md); one
 * that is gone, unreachable or not an id carries `noindex` and the generic title.
 * The server reads it without the viewer's cookies: only what a stranger may see.
 */
export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const result = PUBLIC_ID.test(id) ? await entryOnServer(id) : null;
  if (result === null || !result.ok) {
    return pageMetadata({
      path: path(id),
      title: messages.atlas.title,
      description: messages.atlas.lead,
      noindex: true,
    });
  }
  return pageMetadata({
    path: path(id),
    title: result.data.title,
    description: result.data.glimpse,
    type: 'article',
  });
}

export default async function AtlasEntryPage({ params }: Params) {
  const { id } = await params;
  const result = PUBLIC_ID.test(id) ? await entryOnServer(id) : null;
  return (
    <>
      {result?.ok ? (
        <JsonLd
          data={articleJsonLd({
            path: path(id),
            headline: result.data.title,
            datePublished: result.data.published_at,
            authorName: result.data.author.public_name,
          })}
        />
      ) : null}
      <EntryScreen entryId={id} />
    </>
  );
}
