'use client';

import { type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { useTurnstile } from '@/components/turnstile/use-turnstile';
import { Button } from '@/components/ui/button';
import {
  fetchAccountEmail,
  MESSAGE_MAX,
  MESSAGE_MIN,
  SUPPORT_TOPICS,
  type SupportOutcome,
  type SupportTopic,
  sendSupport,
} from '@/lib/support';
import { legalMessages } from '@/messages/legal';

const T = legalMessages().support;

type Field = 'email' | 'topic' | 'message';
type FieldErrors = Partial<Record<Field, string>>;

// The same shape check the API does in spirit; the server decides in the end.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(email: string, topic: string, message: string): FieldErrors {
  const errors: FieldErrors = {};
  if (email.trim() === '') {
    errors.email = T.errors.emailRequired;
  } else if (!EMAIL.test(email.trim())) {
    errors.email = T.errors.emailInvalid;
  }
  if (topic === '') {
    errors.topic = T.errors.topicRequired;
  }
  const length = message.trim().length;
  if (length < MESSAGE_MIN) {
    errors.message = T.errors.messageShort(MESSAGE_MIN);
  } else if (length > MESSAGE_MAX) {
    errors.message = T.errors.messageLong(MESSAGE_MAX);
  }
  return errors;
}

const RESULT_TEXT: Record<SupportOutcome, string> = {
  sent: T.result.sent,
  invalid: T.result.invalid,
  rate_limited: T.result.rateLimited,
  mail_unavailable: T.result.mailUnavailable,
  turnstile_failed: T.result.turnstileFailed,
  failed: T.result.failed,
};

const CONTROL =
  'w-full rounded-[var(--radius-card)] border border-field bg-surface px-4 text-fg ' +
  'aria-[invalid=true]:border-danger';

interface FieldShellProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  children: ReactNode;
}

function FieldShell({ id, label, hint, error, optional, children }: Readonly<FieldShellProps>) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="font-medium text-fg">
        {label}{' '}
        <span className="font-normal text-fg-muted text-sm">
          ({optional ? T.form.optional : T.form.required})
        </span>
      </label>
      {children}
      {hint === undefined ? null : (
        <p id={`${id}-hint`} className="m-0 text-fg-muted text-sm">
          {hint}
        </p>
      )}
      {error === undefined ? null : (
        <p id={`${id}-error`} className="m-0 font-medium text-danger text-sm">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * The support form (decision 34). It only ever asks the API to e-mail the
 * team; the page says "sent" for a 202 and nothing else, and says honestly
 * when the mail was not sent. The result sits in a live region that exists
 * before it speaks, so a screen reader announces it.
 */
export function SupportForm({ turnstileSiteKey = '' }: Readonly<{ turnstileSiteKey?: string }>) {
  const turnstile = useTurnstile(turnstileSiteKey);
  const base = useId();
  const ids = {
    email: `${base}-email`,
    name: `${base}-name`,
    topic: `${base}-topic`,
    message: `${base}-message`,
    website: `${base}-website`,
  };
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [topic, setTopic] = useState<SupportTopic | ''>('');
  const [message, setMessage] = useState('');
  const [website, setWebsite] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState<SupportOutcome | undefined>();
  const typedEmail = useRef(false);
  const refs = {
    email: useRef<HTMLInputElement>(null),
    topic: useRef<HTMLSelectElement>(null),
    message: useRef<HTMLTextAreaElement>(null),
  };

  // Prefill once for a signed-in reader, never over what the reader already typed.
  useEffect(() => {
    let active = true;
    fetchAccountEmail().then((known) => {
      if (active && known !== undefined && !typedEmail.current) {
        setEmail(known);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate(email, topic, message);
    setErrors(found);
    setOutcome(undefined);
    const firstInvalid = (['email', 'topic', 'message'] as const).find((field) => found[field]);
    if (firstInvalid !== undefined) {
      refs[firstInvalid].current?.focus();
      return;
    }
    setSending(true);
    const headers = await turnstile.headers();
    const result = await sendSupport(
      {
        email: email.trim(),
        ...(name.trim() === '' ? {} : { name: name.trim() }),
        topic: topic as SupportTopic,
        message: message.trim(),
        website,
      },
      headers
    );
    turnstile.reset();
    setSending(false);
    setOutcome(result);
    if (result === 'sent') {
      setMessage('');
    }
  }

  const describedBy = (field: Field, hint: boolean) =>
    [hint ? `${ids[field]}-hint` : undefined, errors[field] ? `${ids[field]}-error` : undefined]
      .filter(Boolean)
      .join(' ') || undefined;
  const summary = Object.values(errors);

  return (
    <form
      aria-label={T.form.label}
      onSubmit={onSubmit}
      noValidate
      className="relative flex flex-col gap-5"
    >
      {summary.length === 0 ? null : (
        <div className="rounded-[var(--radius-card)] border border-danger p-4 text-danger text-sm">
          <p className="m-0 font-medium">{T.errors.summary}</p>
          <ul className="m-0 mt-1 ps-5">
            {summary.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      <FieldShell id={ids.email} label={T.form.email} hint={T.form.emailHint} error={errors.email}>
        <input
          ref={refs.email}
          id={ids.email}
          name="email"
          type="email"
          dir="ltr"
          autoComplete="email"
          inputMode="email"
          value={email}
          aria-required="true"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={describedBy('email', true)}
          onChange={(event) => {
            typedEmail.current = true;
            setEmail(event.target.value);
          }}
          className={`${CONTROL} min-h-12 text-start`}
        />
      </FieldShell>

      <FieldShell id={ids.name} label={T.form.name} optional>
        <input
          id={ids.name}
          name="name"
          type="text"
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className={`${CONTROL} min-h-12`}
        />
      </FieldShell>

      <FieldShell id={ids.topic} label={T.form.topic} error={errors.topic}>
        <select
          ref={refs.topic}
          id={ids.topic}
          name="topic"
          value={topic}
          aria-required="true"
          aria-invalid={errors.topic ? true : undefined}
          aria-describedby={describedBy('topic', false)}
          onChange={(event) => setTopic(event.target.value as SupportTopic | '')}
          className={`${CONTROL} min-h-12`}
        >
          <option value="">{T.form.topicPlaceholder}</option>
          {SUPPORT_TOPICS.map((key) => (
            <option key={key} value={key}>
              {T.topics[key]}
            </option>
          ))}
        </select>
      </FieldShell>

      <FieldShell
        id={ids.message}
        label={T.form.message}
        hint={T.form.messageHint}
        error={errors.message}
      >
        <textarea
          ref={refs.message}
          id={ids.message}
          name="message"
          rows={7}
          value={message}
          aria-required="true"
          aria-invalid={errors.message ? true : undefined}
          aria-describedby={describedBy('message', true)}
          onChange={(event) => setMessage(event.target.value)}
          className={`${CONTROL} min-h-40 py-3 leading-[1.9]`}
        />
        <p className="m-0 text-fg-muted text-sm">{T.form.count(message.length)}</p>
      </FieldShell>

      {/* A honeypot: kept in the DOM and sent, but out of sight, out of reach of a keyboard and hidden from screen readers. */}
      <div aria-hidden="true" className="absolute size-px overflow-hidden start-[-10000px]">
        <label htmlFor={ids.website}>
          {T.honeypotLabel}
          <input
            id={ids.website}
            name="website"
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
          />
        </label>
      </div>

      {turnstile.widget}

      <div>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          disabled={sending}
          aria-disabled={sending}
        >
          {sending ? T.form.sending : T.form.send}
        </Button>
      </div>

      {/* Always in the page, so a screen reader hears what is put into it. */}
      <div role="status" aria-live="polite" data-outcome={outcome} className="min-h-6">
        {outcome === undefined ? null : (
          <p
            className={`m-0 rounded-[var(--radius-card)] border p-4 font-medium ${
              outcome === 'sent' ? 'border-line text-fg' : 'border-danger text-danger'
            }`}
          >
            {RESULT_TEXT[outcome]}
          </p>
        )}
      </div>
    </form>
  );
}
