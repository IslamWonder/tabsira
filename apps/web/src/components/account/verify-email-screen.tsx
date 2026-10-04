'use client';

import Link from 'next/link';
import { useState } from 'react';
import { loadSession, useSession } from '@/account/session';
import { useFragmentToken } from '@/account/use-fragment-token';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { api } from '@/lib/api/client';
import { failureMessage } from '@/lib/api/failure-message';
import { attempt } from '@/lib/api/result';
import { messages } from '@/messages';
import { EmailRequestForm } from './email-request-form';
import { Gate } from './gate';

const T = messages.auth.verify;

type Outcome =
  | { kind: 'idle' | 'sending' | 'done' }
  | { kind: 'failed'; message: string; invalid: boolean };

const resend = (email: string, headers: Record<string, string>) =>
  attempt(api.POST('/auth/resend-verification', { body: { email }, headers }));

/**
 * The page a verification mail links to. The token is read from the
 * fragment, and spent only when the reader presses the one button: a mail
 * scanner that opens the link, even one that runs scripts, cannot use it up.
 * A bad or used link offers a new one at once (tajriba §3.5).
 */
export function VerifyEmailScreen({ turnstileSiteKey = '' }: { turnstileSiteKey?: string }) {
  const link = useFragmentToken();
  const session = useSession();
  const [outcome, setOutcome] = useState<Outcome>({ kind: 'idle' });
  const signedInEmail = session.status === 'signed-in' ? session.user.email : undefined;

  const confirm = async (token: string) => {
    setOutcome({ kind: 'sending' });
    const result = await attempt(api.POST('/auth/verify-email', { body: { token } }));
    if (result.ok) {
      setOutcome({ kind: 'done' });
      // The account now says email_verified; refresh what the pages know of it.
      void loadSession();
      return;
    }
    setOutcome({
      kind: 'failed',
      message: failureMessage(result),
      invalid: result.code === 'INVALID_TOKEN',
    });
  };

  const needsNewLink = link.status === 'missing' || (outcome.kind === 'failed' && outcome.invalid);

  return (
    <Gate
      title={T.title}
      lead={outcome.kind === 'done' || needsNewLink ? undefined : T.lead}
      footer={
        <Link href="/" className="inline-flex min-h-12 items-center text-link">
          {messages.auth.backToScene}
        </Link>
      }
    >
      {link.status === 'missing' ? <Notice tone="info">{T.missing}</Notice> : null}
      {outcome.kind === 'failed' ? (
        <div role="alert">
          <Notice tone="error">{outcome.message}</Notice>
        </div>
      ) : null}
      <div role="status" className="empty:-mb-5">
        {outcome.kind === 'done' ? <Notice tone="success">{T.done}</Notice> : null}
      </div>
      {outcome.kind === 'done' ? (
        <LinkButton href="/me" size="lg" className="w-full">
          {T.openProfile}
        </LinkButton>
      ) : null}
      {link.status === 'found' && outcome.kind !== 'done' && !needsNewLink ? (
        <Button
          size="lg"
          className="w-full"
          disabled={outcome.kind === 'sending'}
          onClick={() => confirm(link.token)}
        >
          {outcome.kind === 'sending' ? T.confirming : T.confirm}
        </Button>
      ) : null}
      {needsNewLink ? (
        <section aria-label={T.resendTitle} className="flex flex-col gap-3">
          <h2 className="m-0 text-fg text-lg">{T.resendTitle}</h2>
          <EmailRequestForm
            request={resend}
            submitLabel={T.resend}
            busyLabel={T.resending}
            acceptedMessage={T.resent}
            defaultEmail={signedInEmail}
            turnstileSiteKey={turnstileSiteKey}
          />
        </section>
      ) : null}
    </Gate>
  );
}
