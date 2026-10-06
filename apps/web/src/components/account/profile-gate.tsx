'use client';

import { usePathname } from 'next/navigation';
import { useId, useState } from 'react';
import { type ProfilePatch, patchProfile } from '@/account/profile';
import { setSignedIn, signOut, type User, useSession } from '@/account/session';
import { Logo } from '@/components/brand/logo';
import { Button } from '@/components/ui/button';
import { FullScreenDialog } from '@/components/ui/full-screen-dialog';
import { GlassPanel } from '@/components/ui/glass-panel';
import { Notice } from '@/components/ui/notice';
import { useConsent } from '@/consent/store';
import { failureMessage } from '@/lib/api/failure-message';
import { messages } from '@/messages';
import { ProfileForm } from './profile-form';

const G = messages.profile.gate;
/** The texts stay readable while the form is up, as under the acceptance of the terms. */
const READABLE = new Set(['/terms', '/privacy']);

function Window({ user }: Readonly<{ user: User }>) {
  const titleId = useId();
  const [leaving, setLeaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const save = async (patch: ProfilePatch): Promise<string | null> => {
    const result = await patchProfile(patch);
    if (!result.ok) {
      return failureMessage(result);
    }
    setSignedIn({ ...user, profile_completed: true });
    return null;
  };

  const leave = async () => {
    setLeaving(true);
    const problem = await signOut();
    setLeaving(false);
    if (problem !== null) {
      setFailure(failureMessage(problem));
    }
  };

  return (
    <FullScreenDialog open layer="z-[65]" labelledBy={titleId}>
      <GlassPanel
        ornate
        className="fx-dialog-surface flex flex-col gap-5 px-5 pt-8 pb-7 tablet:px-10"
      >
        <header className="flex flex-col items-center gap-3 text-center">
          <Logo title={messages.brand.name} className="mb-1 h-20" />
          <h2 id={titleId} className="m-0 font-bold font-display text-title text-gilded">
            {G.title}
          </h2>
        </header>
        <ProfileForm onSubmit={save} />
        {failure === null ? null : (
          <div role="alert">
            <Notice tone="error">{failure}</Notice>
          </div>
        )}
        <div className="flex justify-center border-line border-t pt-3">
          <Button variant="ghost" disabled={leaving} onClick={leave}>
            {G.signOut}
          </Button>
        </div>
      </GlassPanel>
    </FullScreenDialog>
  );
}

/**
 * The full profile form before anything else (decision 64): when `/auth/me` says
 * `profile_completed: false` (a new account, or one made before the rule), a full-screen window
 * asks for the five answers, and the scan and the chat, which the server refuses with 403
 * `profile_required` until then, open it too. The acceptance of the terms comes first; it waits for
 * the cookie choice and never covers the texts it links to.
 */
export function ProfileGate() {
  const session = useSession();
  const pathname = usePathname();
  const { consent, settingsOpen } = useConsent();
  if (
    session.status !== 'signed-in' ||
    session.user.profile_completed ||
    session.user.legal_acceptance_required === true ||
    READABLE.includes(pathname) ||
    consent.status === 'asking' ||
    settingsOpen
  ) {
    return null;
  }
  return <Window user={session.user} />;
}
