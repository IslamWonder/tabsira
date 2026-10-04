'use client';

import type { User } from '@/account/session';
import { LinkButton } from '@/components/ui/button';
import { messages } from '@/messages';
import { SignOutButton } from './sign-out-button';

/** On a sign-in or sign-up page while already signed in: say so, and offer the two ways on. */
export function SignedInNote({ user }: { user: User }) {
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <p className="m-0 text-fg">{messages.auth.signIn.signedInAs(user.display_name)}</p>
      <div className="flex w-full flex-col gap-2.5">
        <LinkButton href="/me" size="lg" className="w-full">
          {messages.auth.signIn.openProfile}
        </LinkButton>
        <SignOutButton className="w-full" />
      </div>
    </div>
  );
}
