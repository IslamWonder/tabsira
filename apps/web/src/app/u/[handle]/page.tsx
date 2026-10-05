import type { Metadata } from 'next';
import { ProfileScreen } from '@/components/community/profile-screen';
import { pageMetadata } from '@/lib/seo';
import { messages } from '@/messages';
import { handleProblem, memberLabel, profilePath } from '@/social/identity';
import { profileOnServer } from '@/social/server';

export const dynamic = 'force-dynamic';

type Params = { params: Promise<{ handle: string }> };

function decode(handle: string): string {
  try {
    return decodeURIComponent(handle);
  } catch {
    return handle;
  }
}

/** A public profile is indexable: its name and handle, nothing else (docs/SEO.md). */
export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const handle = decode((await params).handle);
  // Only a handle of the right shape is asked for: anything else is nobody's page.
  const result = handleProblem(handle) === null ? await profileOnServer(handle) : null;
  if (result === null || !result.ok) {
    return pageMetadata({
      path: profilePath(handle),
      title: messages.community.title,
      description: messages.community.lead,
      noindex: true,
    });
  }
  const label = memberLabel(result.data);
  return pageMetadata({
    path: profilePath(result.data.handle),
    title: label,
    description: messages.community.profileDescription(label),
    type: 'website',
    // The sitemap lists a profile only once it has a public post; results follow the same rule.
    noindex: result.data.posts_count === 0,
  });
}

export default async function ProfilePage({ params }: Params) {
  return <ProfileScreen handle={decode((await params).handle)} />;
}
