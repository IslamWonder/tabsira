'use client';

import { type InputHTMLAttributes, type Ref, useId, useState } from 'react';
import { EyeIcon, EyeOffIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export interface TextFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'className' | 'children'> {
  label: string;
  /** A short rule or reassurance under the label, read with the field. */
  hint?: string;
  /** Why the value was refused; shown under the field and announced with it. */
  error?: string | null;
  /** A password field gets a button that shows what was typed (no confirm field needed). */
  revealable?: boolean;
  ref?: Ref<HTMLInputElement>;
  className?: string;
}

/**
 * A labelled input. The label sits above the field and stays visible while
 * typing (a placeholder is not a label); the hint and the error are tied to
 * the field with aria-describedby, and the error sits right under it (Law of
 * Proximity, tajriba §3.5). 52 px high: an easy target with one thumb.
 */
export function TextField({
  label,
  hint,
  error,
  revealable = false,
  type = 'text',
  dir,
  ref,
  className,
  ...input
}: TextFieldProps) {
  const id = useId();
  const hintId = useId();
  const errorId = useId();
  const [revealed, setRevealed] = useState(false);
  const invalid = typeof error === 'string' && error !== '';
  const describedBy = [hint === undefined ? null : hintId, invalid ? errorId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="font-medium text-[0.9375rem] text-fg">
        {label}
      </label>
      {hint === undefined ? null : (
        <p id={hintId} className="m-0 text-fg-muted text-sm">
          {hint}
        </p>
      )}
      <div className="relative">
        <input
          {...input}
          ref={ref}
          id={id}
          type={revealable && revealed ? 'text' : type}
          dir={dir}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy === '' ? undefined : describedBy}
          className={cx(
            'min-h-[52px] w-full rounded-[14px] border bg-surface px-4 text-base text-fg',
            'transition-[border-color] duration-200 placeholder:text-fg-muted',
            'focus-visible:border-[var(--focus)]',
            revealable && 'pe-14',
            invalid ? 'border-danger' : 'border-field'
          )}
        />
        {revealable ? (
          <button
            type="button"
            aria-pressed={revealed}
            aria-label={
              revealed ? messages.auth.fields.hidePassword : messages.auth.fields.showPassword
            }
            onClick={() => setRevealed((shown) => !shown)}
            className="absolute inset-y-0 end-0 flex w-12 items-center justify-center rounded-e-[14px] text-fg-muted transition-colors duration-200 hover:text-fg"
          >
            {revealed ? <EyeOffIcon width="20" height="20" /> : <EyeIcon width="20" height="20" />}
          </button>
        ) : null}
      </div>
      {invalid ? (
        <p id={errorId} className="m-0 text-danger text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
