import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { EmptyStage } from '@/components/app/empty-stage';
import { AtlasIcon } from '@/components/icons';
import { MapLayout } from '@/components/layout/layouts';
import { ar } from '@/messages/ar';

export const metadata: Metadata = {
  title: ar.nav.atlas,
  alternates: { canonical: '/atlas' },
};

/** The world atlas: a map with a results panel, once built; the map area stays empty until then. */
export default function AtlasPage() {
  return (
    <MapLayout
      mapLabel={ar.pages.atlas.mapLabel}
      mapClassName="hidden tablet:block"
      panel={
        <ComingSoon
          icon={<AtlasIcon width="28" height="28" />}
          title={ar.pages.atlas.title}
          description={ar.pages.atlas.description}
          className="py-10 tablet:py-12"
        />
      }
      map={<EmptyStage icon={<AtlasIcon width="28" height="28" />} />}
      className="pb-nav tablet:pb-0"
    />
  );
}
