'use client';

import Link from 'next/link';
import { type SubmitEvent, useRef, useState } from 'react';
import { useFragmentToken } from '@/account/use-fragment-token';
import { newPasswordProblem } from '@/account/validation';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { api } from '@/lib/api/client';
import { failureMessage } from '@/lib/api/failure-message';
import { attempt, fieldRefused } from '@/lib/api/result';
import { formText } from '@/lib/form-text';
import { messages } from '@/messages';
import { Gate } from './gate';

const T = messages.auth.reset;

type Outcome =
  | { kind: 'idle' | 'sending' | 'done' }
  | { kind: 'failed'; message: string; invalid: boolean };

/**
 * The page a reset mail links to: one new password (with a button to show
 * it, instead of a second field to type it again). It does not sign anyone
 * in; it ends every other session, says so, and leads to the sign-in.
 */
export function ResetPasswordScreen() {
  const link = useFragmentToken();
  const passwordRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome>({ kind: 'idle' });

  const submit = async (event: SubmitEvent<HTMLFormElement>, token: string) => {
    event.preventDefault();
    const password = formText(new FormData(event.currentTarget), 'password');
    const problem = newPasswordProblem(password);
    setError(problem);
    if (problem !== null) {
      passwordRef.current?.focus();
      return;
    }
    setOutcome({ kind: 'sending' });
    const result = await attempt(api.POST('/auth/reset-password', { body: { token, password } }));
    if (result.ok) {
      setOutcome({ kind: 'done' });
      return;
    }
    if (fieldRefused(result, 'password')) {
      setOutcome({ kind: 'idle' });
      setError(messages.auth.validation.passwordLong);
      passwordRef.current?.focus();
      return;
    }
    setOutcome({
      kind: 'failed',
      message: failureMessage(result),
      invalid: result.code === 'INVALID_TOKEN',
    });
  };

  const linkUnusable = link.status === 'missing' || (outcome.kind === 'failed' && outcome.invalid);

  return (
    <Gate
      title={T.title}
      lead={outcome.kind === 'done' || linkUnusable ? undefined : T.lead}
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
        <LinkButton href="/signin" size="lg" className="w-full">
          {T.signIn}
        </LinkButton>
      ) : null}
      {linkUnusable ? (
        <LinkButton href="/forgot-password" size="lg" className="w-full">
          {T.requestNew}
        </LinkButton>
      ) : null}
      {link.status === 'found' && outcome.kind !== 'done' && !linkUnusable ? (
        <form
          noValidate
          onSubmit={(event) => submit(event, link.token)}
          className="flex flex-col gap-4"
          aria-busy={outcome.kind === 'sending'}
        >
          <TextField
            ref={passwordRef}
            name="password"
            type="password"
            autoComplete="new-password"
            dir="auto"
            revealable
            label={messages.auth.fields.newPassword}
            hint={messages.auth.fields.passwordHint}
            error={error}
          />
          <Button type="submit" size="lg" disabled={outcome.kind === 'sending'} className="w-full">
            {outcome.kind === 'sending' ? T.submitting : T.submit}
          </Button>
        </form>
      ) : null}
    </Gate>
  );
}
