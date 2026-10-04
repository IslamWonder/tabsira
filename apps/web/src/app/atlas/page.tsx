import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { EmptyStage } from '@/components/app/empty-stage';
import { AtlasIcon } from '@/components/icons';
import { MapLayout } from '@/components/layout/layouts';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// Outside the sitemap until the atlas has places to list (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({ path: '/atlas', title: messages.nav.atlas });

/** The world atlas: a map with a results panel, once built; the map area stays empty until then. */
export default function AtlasPage() {
  return (
    <MapLayout
      mapLabel={messages.pages.atlas.mapLabel}
      mapClassName="hidden tablet:block"
      panel={
        <ComingSoon
          icon={<AtlasIcon width="28" height="28" />}
          title={messages.pages.atlas.title}
          description={messages.pages.atlas.description}
          className="py-10 tablet:py-12"
        />
      }
      map={<EmptyStage icon={<AtlasIcon width="28" height="28" />} />}
      className="pb-4 tablet:pb-0"
    />
  );
}
