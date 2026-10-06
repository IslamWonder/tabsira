'use client';

import { loadSession, type SessionState, type User } from '@/account/session';
import { SignOutButton } from '@/components/account/sign-out-button';
import { CheckIcon, MailIcon } from '@/components/icons';
import { Button, LinkButton } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { messages } from '@/messages';
import { MeSection } from './me-section';

const M = messages.pages.me;

/**
 * A new link is asked for on /verify-email, where the Turnstile check lives
 * (decision 56 keeps Cloudflare to the five form pages, not /me).
 */
function ResendVerification() {
  return (
    <LinkButton href="/verify-email" variant="secondary" className="self-start">
      <MailIcon width="18" height="18" />
      {M.account.resend}
    </LinkButton>
  );
}

function SignedIn({ user, onSignedOut }: Readonly<{ user: User; onSignedOut: () => void }>) {
  return (
    <div className="flex flex-col gap-5 tablet:flex-row tablet:items-start tablet:justify-between">
      <div className="flex min-w-0 flex-col gap-3">
        <dl className="m-0 flex flex-col gap-3">
          <div className="flex flex-col">
            <dt className="sr-only">{messages.auth.fields.displayName}</dt>
            <dd className="m-0 font-semibold text-fg text-xl">{user.display_name}</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="text-fg-muted text-sm">{M.account.email}</dt>
            <dd className="m-0 flex flex-wrap items-center gap-2">
              <bdi dir="ltr" className="text-fg">
                {user.email}
              </bdi>
              {user.email_verified ? (
                <Chip tone="primary" icon={<CheckIcon width="14" height="14" />}>
                  {M.account.verified}
                </Chip>
              ) : (
                <Chip>{M.account.unverified}</Chip>
              )}
            </dd>
          </div>
        </dl>
        {user.providers.includes('google') ? (
          <p className="m-0 text-fg-muted text-sm">{M.account.withGoogle}</p>
        ) : null}
        {user.email_verified ? null : (
          <div className="flex flex-col gap-2">
            <p className="m-0 text-fg-soft text-sm">{M.account.unverifiedHint}</p>
            <ResendVerification />
          </div>
        )}
      </div>
      <SignOutButton className="tablet:w-56 tablet:shrink-0" onSignedOut={onSignedOut} />
    </div>
  );
}

/**
 * Who is signed in, or the invitation to sign in. An account is optional: a
 * guest keeps every device setting below, and the page says what an account
 * adds without pressing for it (tajriba §2, S10).
 */
export function AccountSection({
  session,
  notice,
  onSignedOut,
}: Readonly<{
  session: SessionState;
  /** What just happened to the account (signed out, deleted), said at the top. */
  notice: string | null;
  onSignedOut: () => void;
}>) {
  return (
    <MeSection id="account" title={M.sections.account}>
      <div role="status" className="empty:-mb-5">
        {notice === null ? null : <Notice tone="success">{notice}</Notice>}
      </div>
      {session.status === 'signed-in' ? (
        <SignedIn user={session.user} onSignedOut={onSignedOut} />
      ) : null}
      {session.status === 'guest' ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <p className="m-0 font-semibold text-fg text-lg">{M.guest.title}</p>
            <p className="m-0 text-fg-soft leading-[1.85]">{M.guest.body}</p>
          </div>
          <div className="grid gap-2.5 tablet:max-w-md tablet:grid-cols-2">
            <LinkButton href="/signin?next=/me">{M.guest.signIn}</LinkButton>
            <LinkButton href="/signup?next=/me" variant="secondary">
              {M.guest.signUp}
            </LinkButton>
          </div>
        </div>
      ) : null}
      {session.status === 'unknown' ? (
        <p role="status" className="m-0 text-fg-muted">
          {M.loading}
        </p>
      ) : null}
      {session.status === 'unavailable' ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <Notice tone="error">{M.unavailable}</Notice>
          <Button variant="ghost" onClick={() => void loadSession()}>
            {M.retry}
          </Button>
        </div>
      ) : null}
    </MeSection>
  );
}
