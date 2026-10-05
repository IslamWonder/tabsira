import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { CameraScreen } from '@/components/atlas/camera-screen';
import { featureEnabled } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// The camera_discovery feature is read on every request, never baked at build time.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = unlistedMetadata({
  path: '/atlas/camera',
  title: messages.atlas.camera.title,
  description: messages.atlas.camera.description,
});

/** The camera discovery; a 404 while the feature is off, as the API's own routes answer. */
export default function AtlasCameraPage() {
  if (!featureEnabled('camera_discovery')) {
    notFound();
  }
  return <CameraScreen />;
}
