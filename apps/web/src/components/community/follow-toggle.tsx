'use client';

import { useState } from 'react';
import { signInHref } from '@/account/links';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { useAccess } from '@/social/access';
import { setFollow } from '@/social/api';
import { profilePath } from '@/social/identity';

const P = messages.community.profile;

export interface FollowToggleProps {
  handle: string;
  follows: boolean;
  onChange: (follows: boolean) => void;
  /**
   * Beside an author's name on a post or an insight: a small button, and nothing at all
   * for a guest or an unverified account (the profile page is where they are told why).
   */
  compact?: boolean;
}

/**
 * Follow or stop following a member: always the reader's own tap, never done
 * for them by a visit. On the profile page it is the main button; beside an
 * author's name it is a quiet one.
 */
export function FollowToggle({
  handle,
  follows,
  onChange,
  compact = false,
}: Readonly<FollowToggleProps>) {
  const access = useAccess();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (access === 'guest') {
    return compact ? null : (
      <LinkButton href={signInHref(profilePath(handle))} variant="secondary">
        {P.signIn}
      </LinkButton>
    );
  }
  if (access === 'unverified' && !follows) {
    return compact ? null : <p className="m-0 text-fg-soft text-sm">{P.verify}</p>;
  }
  const toggle = async () => {
    setBusy(true);
    setFailure(null);
    const result = await setFollow(handle, !follows);
    setBusy(false);
    if (result.ok) {
      onChange(!follows);
    } else {
      setFailure(failureMessage(result));
    }
  };
  const idleVariant = compact ? 'ghost' : 'primary';
  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        variant={follows ? 'secondary' : idleVariant}
        aria-pressed={follows}
        onClick={toggle}
        disabled={busy || access === 'unknown'}
        className={compact ? 'min-h-9 px-3 text-sm' : undefined}
      >
        {follows ? P.following : P.follow}
      </Button>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
    </div>
  );
}
