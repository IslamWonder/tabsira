'use client';

import type { Route } from 'next';
import { useId } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { signUpHref } from '@/lib/scan/gate';
import { messages } from '@/messages';

const T = messages.auth.invitation;

export interface SaveInvitationProps {
  /** Where the reader comes back to after creating the account (the insight they just finished). */
  returnTo: Route;
  className?: string;
}

/**
 * The invitation after the guest's first own insight (decision 63, amending v2 §4.7): create
 * an account to keep it, or sign in to an existing one. There is no «continue as a guest»: a
 * second scan or the chat of this one needs an account, and the insight moves into it. Shown
 * once the insight is done, after the done button.
 */
export function SaveInvitation({ returnTo, className }: SaveInvitationProps) {
  const titleId = useId();
  return (
    <GlassPanel
      as="section"
      ornate
      aria-labelledby={titleId}
      className={cx('flex flex-col items-center gap-4 px-6 py-7 text-center', className)}
    >
      <LogoMark className="h-14" />
      <h2 id={titleId} className="m-0 text-subheading text-fg">
        {T.title}
      </h2>
      <p className="m-0 max-w-md text-[0.9375rem] text-fg-soft leading-[1.85]">{T.body}</p>
      <div className="grid w-full max-w-md gap-2.5 tablet:grid-cols-2">
        <LinkButton href={signUpHref(returnTo)} size="lg">
          {T.save}
        </LinkButton>
        <LinkButton
          href={`/signin?next=${encodeURIComponent(returnTo)}` as Route}
          variant="secondary"
          size="lg"
        >
          {T.signIn}
        </LinkButton>
      </div>
    </GlassPanel>
  );
}
