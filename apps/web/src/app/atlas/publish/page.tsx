import type { Metadata } from 'next';
import { Suspense } from 'react';
import { MapPublishScreen } from '@/components/atlas/map-publish-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// Private to its owner: never indexed.
export const metadata: Metadata = unlistedMetadata({
  path: '/atlas/publish',
  title: messages.atlas.publish.title,
});

/** The screen reads `?insight=` in the browser, so it renders inside a Suspense boundary. */
export default function AtlasPublishPage() {
  return (
    <Suspense fallback={null}>
      <MapPublishScreen />
    </Suspense>
  );
}
