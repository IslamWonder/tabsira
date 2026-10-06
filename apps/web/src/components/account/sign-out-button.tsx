'use client';

import { useState } from 'react';
import { signOut } from '@/account/session';
import { SignOutIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/**
 * Ends the session on this device. Success is shown by the page itself
 * becoming the signed-out page (the session store changes); a failure stays
 * here, under the button, with what to do.
 */
export function SignOutButton({
  className,
  onSignedOut,
}: Readonly<{
  className?: string;
  /** After the session ended, before the page shows the signed-out state. */
  onSignedOut?: () => void;
}>) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const leave = async () => {
    setBusy(true);
    setFailure(null);
    const problem = await signOut(onSignedOut);
    setBusy(false);
    if (problem !== null) {
      setFailure(failureMessage(problem));
    }
  };

  return (
    <div className={cx('flex flex-col gap-2', className)}>
      <Button variant="secondary" onClick={leave} disabled={busy} className="w-full">
        <SignOutIcon width="18" height="18" />
        {busy ? messages.auth.signOut.busy : messages.auth.signOut.action}
      </Button>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </div>
  );
}
