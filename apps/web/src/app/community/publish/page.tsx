import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { Suspense } from 'react';
import { PublishScreen } from '@/components/community/publish-screen';
import { featureEnabled } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// The social feature is read on every request, never baked at build time.
export const dynamic = 'force-dynamic';

// Private to its author: never indexed.
export const metadata: Metadata = unlistedMetadata({
  path: '/community/publish',
  title: messages.community.publish.title,
});

/** The screen reads `?insight=` in the browser, so it renders inside a Suspense boundary; a 404 while the network is off. */
export default function PublishPage() {
  if (!featureEnabled('social')) {
    notFound();
  }
  return (
    <Suspense fallback={null}>
      <PublishScreen comments={featureEnabled('social_comments')} />
    </Suspense>
  );
}
