import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ScanScreen } from '@/components/scan/scan-screen';
import { isPublicId } from '@/lib/scan/ids';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.scan.metaTitle,
  // A person's own scan: never indexed.
  robots: { index: false, follow: false },
};

/** One scan of the visitor (an account or a guest); the API answers only its owner. */
export default async function ScanPage({ params }: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;
  if (!isPublicId(id)) {
    notFound();
  }
  return <ScanScreen scanId={id} />;
}
