import type { Metadata } from 'next';
import { Suspense } from 'react';
import { PublishScreen } from '@/components/community/publish-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// Private to its author: never indexed.
export const metadata: Metadata = unlistedMetadata({
  path: '/community/publish',
  title: messages.community.publish.title,
});

/** The screen reads `?insight=` in the browser, so it renders inside a Suspense boundary. */
export default function PublishPage() {
  return (
    <Suspense fallback={null}>
      <PublishScreen />
    </Suspense>
  );
}
