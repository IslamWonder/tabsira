import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { PublicInsightPage } from '@/components/insight/public-insight';
import { JsonLd } from '@/components/legal/json-ld';
import { loadPublicInsight, publicInsightMetadata, publicInsightPath } from '@/lib/public-insight';
import { isPublicId } from '@/lib/scan/ids';
import { articleJsonLd, breadcrumbJsonLd, unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// Read at each request: a withdrawal must show at once (the API answers no-store).
export const dynamic = 'force-dynamic';

type Props = { params: Promise<{ id: string }> };

async function load(params: Props['params']) {
  const { id } = await params;
  if (!isPublicId(id)) {
    notFound();
  }
  const result = await loadPublicInsight(id);
  if (!result.ok && result.status === 404) {
    // Unknown, unpublished and withdrawn are one answer, with nothing to tell them apart.
    notFound();
  }
  return { id, result };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id, result } = await load(params);
  if (!result.ok) {
    return unlistedMetadata({
      path: publicInsightPath(id),
      title: messages.publicInsight.unavailableTitle,
    });
  }
  return publicInsightMetadata(result.data);
}

/** A published insight, server-rendered so crawlers and share previews read it. */
export default async function PublicInsightRoute({ params }: Props) {
  const { result } = await load(params);
  if (!result.ok) {
    // The API did not answer: the error page, never a "not found" that would be untrue.
    throw new Error(`public insight unavailable: ${result.code}`);
  }
  const insight = result.data;
  const path = publicInsightPath(insight.id);
  return (
    <>
      <JsonLd
        data={articleJsonLd({
          path,
          headline: insight.title,
          datePublished: insight.published_at,
          authorName: insight.author?.public_name,
        })}
      />
      <JsonLd data={breadcrumbJsonLd([{ name: insight.title, path }])} />
      <PublicInsightPage insight={insight} />
    </>
  );
}
