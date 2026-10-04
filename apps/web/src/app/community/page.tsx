import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { CommunityIcon } from '@/components/icons';
import { FeedLayout } from '@/components/layout/layouts';
import { ar } from '@/messages/ar';

export const metadata: Metadata = {
  title: ar.nav.community,
  alternates: { canonical: '/community' },
};

/** The feed column, centred; its tabs and filters will take the side column. */
export default function CommunityPage() {
  return (
    <FeedLayout
      aside={null}
      feed={
        <ComingSoon
          icon={<CommunityIcon width="28" height="28" />}
          title={ar.pages.community.title}
          description={ar.pages.community.description}
          className="py-10 tablet:py-16"
        />
      }
      className="pb-nav tablet:pb-8"
    />
  );
}
