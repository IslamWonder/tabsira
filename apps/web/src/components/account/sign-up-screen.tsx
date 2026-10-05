'use client';

import type { Route } from 'next';
import Link from 'next/link';
import { type FormEvent, useRef, useState } from 'react';
import {
  acceptanceOf,
  LEGAL_REFUSAL,
  type LegalAcceptance,
  type LegalVersions,
} from '@/account/legal';
import { setSignedIn, type User, useSession } from '@/account/session';
import { useLegal } from '@/account/use-legal';
import {
  cleanDisplayName,
  displayNameProblem,
  emailProblem,
  newPasswordProblem,
} from '@/account/validation';
import { track } from '@/analytics/events';
import { MailIcon } from '@/components/icons';
import { useTurnstile } from '@/components/turnstile/use-turnstile';
import { Button, LinkButton } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { api } from '@/lib/api/client';
import { failureMessage } from '@/lib/api/failure-message';
import { attempt, type Failure, fieldRefused } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';
import { messages } from '@/messages';
import { FullNameConsent } from './full-name-consent';
import { Gate } from './gate';
import { GoogleSignIn } from './google-sign-in';
import { LegalConsent } from './legal-consent';
import { SignedInNote } from './signed-in-note';

const T = messages.auth.signUp;
const F = messages.auth.fields;
const V = messages.auth.validation;

type Field = 'displayName' | 'email' | 'password';
/** The generated SignupIn, with decision 35's accepted versions until the schema has them. */
type SignUpBody = components['schemas']['SignupIn'] & LegalAcceptance;
type FieldErrors = Partial<Record<Field, string | null>>;

/** The field a refused request points at, with the sentence for it. */
function refusedField(failure: Failure): [Field, string] | null {
  if (fieldRefused(failure, 'display_name')) {
    return ['displayName', V.nameInvalid];
  }
  if (fieldRefused(failure, 'email')) {
    return ['email', V.emailInvalid];
  }
  return fieldRefused(failure, 'password') ? ['password', V.passwordLong] : null;
}

/**
 * Create an account: the full name, an address and a password, and the separate, unticked
 * box for showing the name (decision 63). The profile questions come right after, in the
 * mandatory profile step. The new account is signed in at once; the address is confirmed by the mailed link, needed
 * only before publishing (owner decision 25).
 */
export function SignUpScreen({
  next,
  turnstileSiteKey = '',
}: {
  next: Route;
  /** Cloudflare Turnstile's site key from the web server; empty means no check (decision 56). */
  turnstileSiteKey?: string;
}) {
  const session = useSession();
  const turnstile = useTurnstile(turnstileSiteKey);
  const refs = {
    displayName: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
  };
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [created, setCreated] = useState<User | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [fullName, setFullName] = useState(false);
  const legal = useLegal();

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const displayName = cleanDisplayName(String(form.get('displayName')));
    const email = String(form.get('email')).trim();
    const password = String(form.get('password'));
    const found: FieldErrors = {
      displayName: displayNameProblem(displayName),
      email: emailProblem(email),
      password: newPasswordProblem(password),
    };
    setErrors(found);
    setFailure(null);
    const first = (Object.keys(found) as Field[]).find((field) => found[field] !== null);
    if (first !== undefined) {
      refs[first].current?.focus();
      return;
    }
    // The button is enabled only once the box is ticked and the versions are known.
    const versions = (legal.state as { status: 'ready'; legal: LegalVersions }).legal;
    const body: SignUpBody = {
      email,
      password,
      display_name: displayName,
      public_full_name: fullName,
      ...acceptanceOf(versions),
    };
    setSending(true);
    const headers = await turnstile.headers();
    const result = await attempt(api.POST('/auth/signup', { body, headers }));
    turnstile.reset();
    setSending(false);
    if (!result.ok && result.code === LEGAL_REFUSAL) {
      // The texts changed while the form was open: read them again, ask again.
      setAccepted(false);
      legal.reload();
    }
    if (result.ok) {
      setSignedIn(result.data);
      setCreated(result.data);
      track('sign_up_completed', { method: 'email' });
      return;
    }
    const refused = refusedField(result);
    if (refused !== null) {
      setErrors({ [refused[0]]: refused[1] });
      refs[refused[0]].current?.focus();
      return;
    }
    setFailure(failureMessage(result));
  };

  if (created !== null) {
    return (
      <Gate title={T.doneTitle}>
        <div role="status" className="flex flex-col gap-4">
          <Notice tone="success">
            <p className="m-0">{T.doneBody(created.email)}</p>
          </Notice>
          <p className="m-0 flex items-start gap-2 text-fg-muted text-sm leading-[1.8]">
            <MailIcon width="18" height="18" className="mt-1 shrink-0" />
            {T.doneHint}
          </p>
        </div>
        <LinkButton href={next} size="lg" className="w-full">
          {T.continue}
        </LinkButton>
      </Gate>
    );
  }

  return (
    <Gate
      title={T.title}
      lead={T.lead}
      footer={
        <>
          <p className="m-0">
            {T.haveAccount}{' '}
            <Link
              href={`/signin?next=${encodeURIComponent(next)}` as Route}
              className="inline-flex min-h-12 items-center font-semibold text-link"
            >
              {T.signIn}
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
          <form noValidate onSubmit={submit} className="flex flex-col gap-4" aria-busy={sending}>
            <TextField
              ref={refs.displayName}
              name="displayName"
              autoComplete="name"
              maxLength={120}
              label={F.displayName}
              hint={F.displayNameHint}
              error={errors.displayName}
            />
            <TextField
              ref={refs.email}
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              dir="ltr"
              label={F.email}
              error={errors.email}
            />
            <TextField
              ref={refs.password}
              name="password"
              type="password"
              autoComplete="new-password"
              dir="auto"
              revealable
              label={F.password}
              hint={F.passwordHint}
              error={errors.password}
            />
            <FullNameConsent checked={fullName} onChange={setFullName} />
            <LegalConsent
              checked={accepted}
              onChange={setAccepted}
              disabled={legal.state.status !== 'ready'}
            />
            {legal.state.status === 'failed' ? (
              <div role="alert" className="flex flex-col items-start gap-1">
                <Notice tone="error">{messages.auth.legal.unavailable}</Notice>
                <Button variant="ghost" onClick={legal.reload}>
                  {messages.auth.legal.retry}
                </Button>
              </div>
            ) : null}
            {turnstile.widget}
            {failure === null ? null : (
              <div role="alert">
                <Notice tone="error">{failure}</Notice>
              </div>
            )}
            <Button
              type="submit"
              size="lg"
              disabled={sending || !accepted || legal.state.status !== 'ready'}
              className="w-full"
            >
              {sending ? T.submitting : T.submit}
            </Button>
          </form>
          <GoogleSignIn
            next={next}
            divider="before"
            accepted={accepted && legal.state.status === 'ready' ? legal.state.legal : null}
            publicFullName={fullName}
          />
        </>
      )}
    </Gate>
  );
}
