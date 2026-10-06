import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { Suspense } from 'react';
import { MapPublishScreen } from '@/components/atlas/map-publish-screen';
import { featureEnabled } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// The atlas feature is read on every request, never baked at build time.
export const dynamic = 'force-dynamic';

// Private to its owner: never indexed.
export const metadata: Metadata = unlistedMetadata({
  path: '/atlas/publish',
  title: messages.atlas.publish.title,
});

/** The screen reads `?insight=` in the browser, so it renders inside a Suspense boundary; a 404 while the atlas is off. */
export default function AtlasPublishPage() {
  if (!featureEnabled('atlas')) {
    notFound();
  }
  return (
    <Suspense fallback={null}>
      <MapPublishScreen community={featureEnabled('social')} />
    </Suspense>
  );
}
