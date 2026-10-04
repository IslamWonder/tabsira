import type { Metadata } from 'next';
import { ProfileScreen } from '@/components/community/profile-screen';
import { pageMetadata } from '@/lib/seo';
import { messages } from '@/messages';
import { profilePath } from '@/social/identity';
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
  const result = await profileOnServer(handle);
  if (!result.ok) {
    return pageMetadata({
      path: profilePath(handle),
      title: messages.community.title,
      description: messages.community.lead,
      noindex: true,
    });
  }
  return pageMetadata({
    path: profilePath(result.data.handle),
    title: result.data.public_name,
    description: messages.community.profileDescription(result.data.public_name),
    type: 'website',
  });
}

export default async function ProfilePage({ params }: Params) {
  return <ProfileScreen handle={decode((await params).handle)} />;
}
