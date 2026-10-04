import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { PublicInsightArticle } from '@/components/public-insight/public-insight-article';
import { fetchPublicInsight, publicInsightSeo } from '@/lib/public-insight';
import { isPublicId } from '@/lib/scan/ids';
import { pageMetadata } from '@/lib/seo';

/*
 * The public page of a published insight (master prompt v2 §18). The web server
 * asks the API, which answers only for an insight its owner made public; anything
 * else is the not-found page, the same for a private, a withdrawn and a missing one.
 */

type Params = { params: Promise<{ id: string }> };

async function load(params: Params['params']) {
  const { id } = await params;
  if (!isPublicId(id)) {
    notFound();
  }
  const insight = await fetchPublicInsight(id);
  if (insight === null) {
    notFound();
  }
  return insight;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  return pageMetadata(publicInsightSeo(await load(params)));
}

export default async function PublicInsightPage({ params }: Params) {
  return <PublicInsightArticle insight={await load(params)} />;
}
