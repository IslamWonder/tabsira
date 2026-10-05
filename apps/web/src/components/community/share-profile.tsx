'use client';

import { useState } from 'react';
import { ShareIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { type Said, shareLink } from '@/lib/share-link';
import { siteOrigin } from '@/lib/site';
import { messages } from '@/messages';
import { profilePath } from '@/social/identity';

const P = messages.community.profile;

export interface ShareProfileProps {
  handle: string;
  /** The name shown on the page: the public name, or the handle. */
  label: string;
  /** The owner is asked to share their page; anyone else to share this one. */
  own: boolean;
  variant?: 'secondary' | 'ghost';
}

/**
 * Shares a public profile so others can follow it: the phone's share dialog
 * (WhatsApp, Telegram, mail...) where there is one, else the link copied, and
 * one quiet line saying so. The address is the profile's public page only.
 */
export function ShareProfile({ handle, label, own, variant = 'secondary' }: ShareProfileProps) {
  const [said, setSaid] = useState<Said | null>(null);
  const share = async () => {
    const url = new URL(profilePath(handle), siteOrigin()).toString();
    setSaid(await shareLink(P.shareTitle(label), url));
  };
  return (
    <div className="flex flex-col items-start gap-2">
      <Button variant={variant} onClick={() => void share()}>
        <ShareIcon width="18" height="18" aria-hidden="true" />
        {own ? P.shareOwn : P.shareOther}
      </Button>
      <div role="status">
        {said === null ? null : <Notice tone={said.tone}>{said.text}</Notice>}
      </div>
    </div>
  );
}
