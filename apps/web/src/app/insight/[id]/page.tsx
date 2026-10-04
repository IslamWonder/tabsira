import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { InsightScreen } from '@/components/insight/insight-screen';
import { isPublicId } from '@/lib/scan/ids';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.insightPage.metaTitle,
  // A person's own insight: never indexed.
  robots: { index: false, follow: false },
};

/** One insight of the visitor (an account or a guest); the API answers only its owner. */
export default async function InsightPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isPublicId(id)) {
    notFound();
  }
  return <InsightScreen insightId={id} />;
}
