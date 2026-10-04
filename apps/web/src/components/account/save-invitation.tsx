'use client';

import type { Route } from 'next';
import { useId } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { Button, LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

const T = messages.auth.invitation;

export interface SaveInvitationProps {
  /** Where the reader comes back to after creating the account (the insight they just finished). */
  returnTo: Route;
  /** Continuing as a guest: closes the invitation; it is not asked again in this visit. */
  onContinueAsGuest: () => void;
  className?: string;
}

/**
 * The soft invitation after the first completed insight (master prompt v2
 * §4.7, tajriba S10): a question, two equal answers, no pressure. Never shown
 * before the first insight, never a wall: the guest goes on exactly as before
 * (Flow, tajriba LUX-08). Ready here; the insight screen places it after the done button.
 */
export function SaveInvitation({ returnTo, onContinueAsGuest, className }: SaveInvitationProps) {
  const titleId = useId();
  return (
    <GlassPanel
      as="section"
      ornate
      aria-labelledby={titleId}
      className={cx('flex flex-col items-center gap-4 px-6 py-7 text-center', className)}
    >
      <LogoMark className="h-14" />
      <h2 id={titleId} className="m-0 text-[1.25rem] text-fg leading-[1.6]">
        {T.title}
      </h2>
      <p className="m-0 max-w-md text-[0.9375rem] text-fg-soft leading-[1.85]">{T.body}</p>
      <div className="grid w-full max-w-md gap-2.5 tablet:grid-cols-2">
        <LinkButton
          href={`/signup?next=${encodeURIComponent(returnTo)}` as Route}
          variant="secondary"
          size="lg"
        >
          {T.save}
        </LinkButton>
        <Button variant="secondary" size="lg" onClick={onContinueAsGuest}>
          {T.guest}
        </Button>
      </div>
    </GlassPanel>
  );
}
