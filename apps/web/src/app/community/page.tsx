import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { CommunityIcon } from '@/components/icons';
import { FeedLayout } from '@/components/layout/layouts';
import { messages } from '@/messages';

export const metadata: Metadata = {
  title: messages.nav.community,
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
          title={messages.pages.community.title}
          description={messages.pages.community.description}
          className="py-10 tablet:py-16"
        />
      }
      className="pb-4 tablet:pb-8"
    />
  );
}
