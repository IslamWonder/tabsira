import type { Metadata } from 'next';
import { CommunityScreen } from '@/components/community/community-screen';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// The feeds change by the minute; the sitemap lists the posts themselves (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({
  path: '/community',
  title: messages.community.title,
  description: messages.community.lead,
});

export default function CommunityPage() {
  return <CommunityScreen />;
}
