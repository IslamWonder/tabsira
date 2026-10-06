import type { Metadata } from 'next';
import { entryOnServer } from '@/atlas/server';
import { EntryScreen } from '@/components/atlas/entry-screen';
import { JsonLd } from '@/components/legal/json-ld';
import { featureEnabled } from '@/config/server-env';
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
 * One whose place was widened (an orphan, or one a member sponsors) is anonymous and
 * carries `noindex` too, so that a search engine does not keep it beside a person.
 * The server reads it without the viewer's cookies: only what a stranger may see.
 */
export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  const result = PUBLIC_ID.test(id) ? await entryOnServer(id) : null;
  if (!result?.ok) {
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
    noindex: result.data.location.widened_level != null,
  });
}

export default async function AtlasEntryPage({ params }: Readonly<Params>) {
  const { id } = await params;
  const result = PUBLIC_ID.test(id) ? await entryOnServer(id) : null;
  return (
    <>
      {result?.ok ? (
        <JsonLd
          data={articleJsonLd({
            path: path(id),
            headline: result.data.title,
            datePublished: result.data.published_on,
            ...(result.data.author === null
              ? {}
              : { authorName: result.data.author.public_name ?? undefined }),
          })}
        />
      ) : null}
      <EntryScreen
        entryId={id}
        sponsorship={featureEnabled('atlas_sponsorship')}
        social={featureEnabled('social')}
      />
    </>
  );
}
