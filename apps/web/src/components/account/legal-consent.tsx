'use client';

import { useId } from 'react';
import { CheckIcon } from '@/components/icons';
import { messages } from '@/messages';

const L = messages.auth.legal;

function TextLink({
  href,
  inPlace,
  children,
}: Readonly<{
  href: '/terms' | '/privacy';
  inPlace: boolean;
  children: string;
}>) {
  const classes = 'font-semibold text-link underline underline-offset-4';
  if (inPlace) {
    return (
      <a href={href} className={classes}>
        {children}
      </a>
    );
  }
  // A new tab, so what was typed in the form is still there when the reader comes back.
  return (
    <a href={href} target="_blank" rel="noopener" className={classes}>
      {children}
      <span className="sr-only"> {messages.a11y.opensInNewTab}</span>
    </a>
  );
}

export interface LegalConsentProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  /** The texts open in this tab (the gate, which steps aside on them) rather than a new one (a form). */
  inPlace?: boolean;
}

/**
 * «I accept the terms of use and the privacy policy», unticked until the reader ticks
 * it (owner decision 35), each text a link. A native checkbox under a 24 px
 * box, inside a 48 px row: Space toggles it and screen readers say its state.
 */
export function LegalConsent({
  checked,
  onChange,
  disabled = false,
  inPlace = false,
}: Readonly<LegalConsentProps>) {
  const id = useId();
  return (
    <div className="flex min-h-12 items-start gap-3">
      <span className="relative mt-1 flex size-6 shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="peer size-6 cursor-pointer appearance-none rounded-md border-[1.5px] border-[var(--secondary-border)] bg-surface checked:border-transparent checked:bg-[var(--primary-fill-to)] disabled:cursor-not-allowed disabled:opacity-60"
        />
        <CheckIcon
          width="16"
          height="16"
          className="pointer-events-none absolute inset-0 m-auto hidden text-[var(--on-primary)] peer-checked:block"
        />
      </span>
      <label htmlFor={id} className="cursor-pointer text-[0.9375rem] text-fg leading-[1.85]">
        {L.before}
        <TextLink href="/terms" inPlace={inPlace}>
          {L.terms}
        </TextLink>
        {L.and}
        <TextLink href="/privacy" inPlace={inPlace}>
          {L.privacy}
        </TextLink>
      </label>
    </div>
  );
}
