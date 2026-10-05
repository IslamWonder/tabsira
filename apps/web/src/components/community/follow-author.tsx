'use client';

import { useEffect, useState } from 'react';
import { useSession } from '@/account/session';
import { getProfile } from '@/social/api';
import { FollowToggle } from './follow-toggle';

/**
 * The follow button beside the author of a public insight page. The page is
 * the same for everyone, so whether the reader follows the author is asked
 * once they are known to be signed in; nothing shows for a guest, for the
 * author, or while it is not known.
 */
export function FollowAuthor({ handle }: { handle: string }) {
  const session = useSession();
  const [follows, setFollows] = useState<boolean | null>(null);
  const signedIn = session.status === 'signed-in';

  useEffect(() => {
    if (!signedIn) {
      return undefined;
    }
    let current = true;
    void getProfile(handle).then((result) => {
      const viewer = result.ok ? result.data.viewer : null;
      if (current && viewer !== null && viewer !== undefined && !viewer.is_self) {
        setFollows(viewer.follows);
      }
    });
    return () => {
      current = false;
    };
  }, [handle, signedIn]);

  if (!signedIn || follows === null) {
    return null;
  }
  return <FollowToggle handle={handle} follows={follows} onChange={setFollows} compact />;
}
