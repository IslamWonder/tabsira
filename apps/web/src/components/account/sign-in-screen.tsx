'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useRef, useState } from 'react';
import { setSignedIn, useSession } from '@/account/session';
import { emailProblem, passwordMissing } from '@/account/validation';
import { useTurnstile } from '@/components/turnstile/use-turnstile';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { api } from '@/lib/api/client';
import { failureMessage } from '@/lib/api/failure-message';
import { attempt, fieldRefused } from '@/lib/api/result';
import { messages } from '@/messages';
import { Gate } from './gate';
import { GoogleSignIn } from './google-sign-in';
import { SignedInNote } from './signed-in-note';

const T = messages.auth.signIn;
const F = messages.auth.fields;

export type GoogleErrorCode = keyof typeof messages.auth.google.errors;

export interface SignInScreenProps {
  /** Where to go once signed in (already made safe by the page). */
  next: Route;
  /** A failed Google sign-in, as the API's callback reported it. */
  googleError?: GoogleErrorCode | null;
  /** Cloudflare Turnstile's site key from the web server; empty means no check (decision 56). */
  turnstileSiteKey?: string;
}

/**
 * Sign in (S10): Google when it is available, then the e-mail and the
 * password, one primary button in the thumb zone (Fitts), and the ways out
 * just below: a forgotten password, a new account, back to the scene. The
 * account is optional, and the screen says so.
 */
export function SignInScreen({
  next,
  googleError = null,
  turnstileSiteKey = '',
}: SignInScreenProps) {
  const router = useRouter();
  const session = useSession();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});
  const [failure, setFailure] = useState<string | null>(
    googleError === null ? null : messages.auth.google.errors[googleError]
  );
  const [sending, setSending] = useState(false);
  const turnstile = useTurnstile(turnstileSiteKey);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get('email')).trim();
    const password = String(form.get('password'));
    const found = { email: emailProblem(email), password: passwordMissing(password) };
    setErrors(found);
    setFailure(null);
    if (found.email !== null || found.password !== null) {
      (found.email === null ? passwordRef : emailRef).current?.focus();
      return;
    }
    setSending(true);
    const headers = await turnstile.headers();
    const result = await attempt(api.POST('/auth/login', { body: { email, password }, headers }));
    turnstile.reset();
    setSending(false);
    if (result.ok) {
      setSignedIn(result.data);
      router.replace(next);
      return;
    }
    if (fieldRefused(result, 'email')) {
      setErrors({ email: messages.auth.validation.emailInvalid });
      emailRef.current?.focus();
      return;
    }
    setFailure(failureMessage(result));
  };

  return (
    <Gate
      title={T.title}
      lead={T.lead}
      footer={
        <>
          <p className="m-0">
            {T.noAccount}{' '}
            <Link
              href={`/signup?next=${encodeURIComponent(next)}` as Route}
              className="inline-flex min-h-12 items-center font-semibold text-link"
            >
              {T.createAccount}
            </Link>
          </p>
          <p className="m-0 max-w-sm text-fg-muted text-sm">{messages.auth.optional}</p>
          <Link href="/" className="inline-flex min-h-12 items-center text-link">
            {messages.auth.backToScene}
          </Link>
        </>
      }
    >
      {session.status === 'signed-in' ? (
        <SignedInNote user={session.user} />
      ) : (
        <>
          <GoogleSignIn next={next} divider="after" />
          <form noValidate onSubmit={submit} className="flex flex-col gap-4" aria-busy={sending}>
            <TextField
              ref={emailRef}
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              dir="ltr"
              label={F.email}
              error={errors.email}
            />
            <TextField
              ref={passwordRef}
              name="password"
              type="password"
              autoComplete="current-password"
              dir="auto"
              revealable
              label={F.password}
              error={errors.password}
            />
            <Link
              href="/forgot-password"
              className="-mt-2 inline-flex min-h-12 items-center self-start text-[0.9375rem] text-link"
            >
              {T.forgot}
            </Link>
            {turnstile.widget}
            {failure === null ? null : (
              <div role="alert">
                <Notice tone="error">{failure}</Notice>
              </div>
            )}
            <Button type="submit" size="lg" disabled={sending} className="w-full">
              {sending ? T.submitting : T.submit}
            </Button>
          </form>
        </>
      )}
    </Gate>
  );
}
