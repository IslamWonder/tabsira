'use client';

import { type FormEvent, useRef, useState } from 'react';
import { emailProblem } from '@/account/validation';
import { useTurnstile } from '@/components/turnstile/use-turnstile';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { failureMessage } from '@/lib/api/failure-message';
import { fieldRefused, type Result } from '@/lib/api/result';
import { messages } from '@/messages';

export interface EmailRequestFormProps {
  /** Mails a link to the address; the API answers the same whether or not it has an account. */
  request: (email: string, headers: Record<string, string>) => Promise<Result<unknown>>;
  submitLabel: string;
  busyLabel: string;
  /** Said once the API accepted: never «sent», since the answer does not say whether a mail left. */
  acceptedMessage: string;
  defaultEmail?: string;
  /** Cloudflare Turnstile's site key from the web server; empty means no check (decision 56). */
  turnstileSiteKey?: string;
}

/**
 * One address and one button, for the routes that mail a link (a new
 * verification link, a password reset). Their answer is the same for every
 * address, so the message says what will happen if the address has an
 * account, nothing more (docs/AUTH.md).
 */
export function EmailRequestForm({
  request,
  submitLabel,
  busyLabel,
  acceptedMessage,
  defaultEmail,
  turnstileSiteKey = '',
}: Readonly<EmailRequestFormProps>) {
  const turnstile = useTurnstile(turnstileSiteKey);
  const emailRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [state, setState] = useState<'idle' | 'sending' | 'accepted'>('idle');

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get('email')).trim();
    const problem = emailProblem(email);
    setError(problem);
    setFailure(null);
    if (problem !== null) {
      emailRef.current?.focus();
      return;
    }
    setState('sending');
    const result = await request(email, await turnstile.headers());
    turnstile.reset();
    if (result.ok) {
      setState('accepted');
      return;
    }
    setState('idle');
    if (fieldRefused(result, 'email')) {
      setError(messages.auth.validation.emailInvalid);
      emailRef.current?.focus();
      return;
    }
    setFailure(failureMessage(result));
  };

  return (
    <form
      noValidate
      onSubmit={submit}
      className="flex flex-col gap-4"
      aria-busy={state === 'sending'}
    >
      <TextField
        ref={emailRef}
        name="email"
        type="email"
        inputMode="email"
        autoComplete="email"
        dir="ltr"
        defaultValue={defaultEmail}
        label={messages.auth.fields.email}
        error={error}
      />
      {turnstile.widget}
      {/* Always present, so the message is announced when it arrives; empty, it takes no room. */}
      <div role="status" className="empty:-mb-4">
        {state === 'accepted' ? <Notice tone="success">{acceptedMessage}</Notice> : null}
      </div>
      {failure === null ? null : (
        <div role="alert">
          <Notice tone="error">{failure}</Notice>
        </div>
      )}
      <Button
        type="submit"
        variant={state === 'accepted' ? 'secondary' : 'primary'}
        size="lg"
        disabled={state === 'sending'}
        className="w-full"
      >
        {state === 'sending' ? busyLabel : submitLabel}
      </Button>
    </form>
  );
}
