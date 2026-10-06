'use client';

import { type ReactNode, useId } from 'react';
import { CheckIcon } from '@/components/icons';

export interface CheckboxFieldProps {
  label: string;
  /** One line under the label saying what ticking it does; read with the box by screen readers. */
  hint?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/**
 * A single yes/no choice inside a form, unticked until the reader ticks it: a
 * native checkbox under a 24 px box inside a 48 px row, the same box as the
 * legal consent (Law of Similarity). Space toggles it, screen readers say its
 * state and its hint, and hover changes nothing.
 */
export function CheckboxField({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: Readonly<CheckboxFieldProps>) {
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
          aria-describedby={hint === undefined ? undefined : hintId}
          onChange={(event) => onChange(event.target.checked)}
          className="peer size-6 cursor-pointer appearance-none rounded-md border-[1.5px] border-[var(--secondary-border)] bg-surface checked:border-transparent checked:bg-[var(--primary-fill-to)] disabled:cursor-not-allowed disabled:opacity-60"
        />
        <CheckIcon
          width="16"
          height="16"
          className="pointer-events-none absolute inset-0 m-auto hidden text-[var(--on-primary)] peer-checked:block"
        />
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <label htmlFor={id} className="cursor-pointer font-semibold text-fg leading-[1.85]">
          {label}
        </label>
        {hint === undefined ? null : (
          <p id={hintId} className="m-0 text-fg-muted text-sm leading-[1.8]">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}
