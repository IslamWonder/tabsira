'use client';

import { useSession } from '@/account/session';
import { hasIdentity, useIdentity } from './identity-store';

/*
 * What the viewer may do on the network, as the API will decide it: a guest
 * reads; a signed-in account with an unverified address reads and saves; a
 * verified one likes, follows and reports; one with a public identity posts
 * and comments. The screens use this only to say, before a request, which
 * step is missing (tajriba §3.5); the API checks it again on every call.
 */
export type Access = 'unknown' | 'guest' | 'unverified' | 'no-identity' | 'member';

export function useAccess(): Access {
  const session = useSession();
  const identity = useIdentity();
  if (session.status === 'unknown' || session.status === 'unavailable') {
    return 'unknown';
  }
  if (session.status === 'guest') {
    return 'guest';
  }
  if (!session.user.email_verified) {
    return 'unverified';
  }
  if (identity.status === 'loading' || identity.status === 'unknown') {
    return 'unknown';
  }
  return hasIdentity(identity) ? 'member' : 'no-identity';
}
