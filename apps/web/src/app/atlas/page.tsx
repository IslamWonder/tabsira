import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { AtlasScreen } from '@/components/atlas/atlas-screen';
import { featureEnabled } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// The atlas and camera_discovery features are read on every request, never baked at build time.
export const dynamic = 'force-dynamic';

// The map itself changes with every window; the sitemap lists the place pages (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({
  path: '/atlas',
  title: messages.atlas.title,
  description: messages.atlas.lead,
});

/** The atlas; a 404 while the feature is off (decision 1), as the API's own routes answer. */
export default function AtlasPage() {
  if (!featureEnabled('atlas')) {
    notFound();
  }
  return (
    <AtlasScreen
      cameraDiscovery={featureEnabled('camera_discovery')}
      sponsorship={featureEnabled('atlas_sponsorship')}
    />
  );
}
