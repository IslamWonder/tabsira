import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { CommunityScreen } from '@/components/community/community-screen';
import { featureSocial } from '@/config/server-env';
import { unlistedMetadata } from '@/lib/seo';
import { messages } from '@/messages';

// FEATURE_SOCIAL is read on every request, never baked at build time.
export const dynamic = 'force-dynamic';

// The feeds change by the minute; the sitemap lists the posts themselves (docs/SEO.md §1).
export const metadata: Metadata = unlistedMetadata({
  path: '/community',
  title: messages.community.title,
  description: messages.community.lead,
});

/** The network's feeds; a 404 while the feature is off (decision 1), as the API's own routes answer. */
export default function CommunityPage() {
  if (!featureSocial()) {
    notFound();
  }
  return <CommunityScreen />;
}
