'use client';

import { useId } from 'react';
import { CheckIcon } from '@/components/icons';
import { messages } from '@/messages';

const T = messages.auth.fullName;

export interface FullNameConsentProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/**
 * «I agree that my full name appears with my posts» (decision 63): its own box, never
 * ticked for the person, never required, and separate from the terms. A native checkbox
 * under a 24 px mark inside a 48 px row, like the terms box.
 */
export function FullNameConsent({ checked, onChange, disabled = false }: FullNameConsentProps) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="flex min-h-12 items-start gap-3">
      <span className="relative mt-1 flex size-6 shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-describedby={hintId}
          onChange={(event) => onChange(event.target.checked)}
          className="peer size-6 cursor-pointer appearance-none rounded-md border-[1.5px] border-[var(--secondary-border)] bg-surface checked:border-transparent checked:bg-[var(--primary-fill-to)] disabled:cursor-not-allowed disabled:opacity-60"
        />
        <CheckIcon
          width="16"
          height="16"
          className="pointer-events-none absolute inset-0 m-auto hidden text-[var(--on-primary)] peer-checked:block"
        />
      </span>
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="cursor-pointer text-[0.9375rem] text-fg leading-[1.85]">
          {T.label}
        </label>
        <p id={hintId} className="m-0 text-fg-muted text-sm leading-[1.8]">
          {T.hint}
        </p>
      </div>
    </div>
  );
}
