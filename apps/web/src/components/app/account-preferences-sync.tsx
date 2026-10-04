'use client';

import { useEffect } from 'react';
import { useSession } from '@/account/session';
import { syncFromAccount } from '@/preferences/account-sync';

/** After a sign-in (or a page load while signed in), the account's theme and motion win. */
export function AccountPreferencesSync() {
  const session = useSession();
  const userId = session.status === 'signed-in' ? session.user.id : null;
  useEffect(() => {
    if (userId !== null) {
      void syncFromAccount();
    }
  }, [userId]);
  return null;
}
