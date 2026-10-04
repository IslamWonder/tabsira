import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { EmptyStage } from '@/components/app/empty-stage';
import { WorldIcon } from '@/components/icons';
import { MapLayout } from '@/components/layout/layouts';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.nav.world,
  alternates: { canonical: '/world' },
  // A personal space: never indexed.
  robots: { index: false, follow: false },
};

/** The fog map with its places as a side list, once built; the map area stays empty until then. */
export default function WorldPage() {
  return (
    <MapLayout
      mapLabel={messages.pages.world.mapLabel}
      mapClassName="hidden tablet:block"
      panel={
        <ComingSoon
          icon={<WorldIcon width="28" height="28" />}
          title={messages.pages.world.title}
          description={messages.pages.world.description}
          className="py-10 tablet:py-12"
        />
      }
      map={<EmptyStage icon={<WorldIcon width="28" height="28" />} />}
      className="pb-4 tablet:pb-0"
    />
  );
}
