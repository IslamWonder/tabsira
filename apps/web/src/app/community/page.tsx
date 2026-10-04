import type { Metadata } from 'next';
import { ComingSoon } from '@/components/app/coming-soon';
import { CommunityIcon } from '@/components/icons';
import { FeedLayout } from '@/components/layout/layouts';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// Outside the sitemap until there are public posts to list (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({
  path: '/community',
  title: messages.nav.community,
});

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
