import type { Metadata } from 'next';
import { AtlasScreen } from '@/components/atlas/atlas-screen';
import { featureCameraDiscovery } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// FEATURE_CAMERA_DISCOVERY decides whether the camera button shows; it is read on every request.
export const dynamic = 'force-dynamic';

// The map itself changes with every window; the sitemap lists the place pages (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({
  path: '/atlas',
  title: messages.atlas.title,
  description: messages.atlas.lead,
});

export default function AtlasPage() {
  return <AtlasScreen cameraDiscovery={featureCameraDiscovery()} />;
}
