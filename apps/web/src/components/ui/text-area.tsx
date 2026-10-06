'use client';

import { type Ref, type TextareaHTMLAttributes, useId } from 'react';
import { cx } from '@/lib/cx';

export interface TextAreaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id' | 'className' | 'children'> {
  label: string;
  /** A short rule under the label, read with the field. */
  hint?: string;
  /** Why the value was refused; shown under the field and announced with it. */
  error?: string | null;
  /** The most characters the API accepts: shows what is left, counted in characters. */
  maxChars?: number;
  /** The current value, needed with `maxChars` to count. */
  value?: string;
  ref?: Ref<HTMLTextAreaElement>;
  className?: string;
}

/**
 * A labelled multi-line field, the same anatomy as TextField (Law of
 * Similarity): the label above and visible while typing, hint and error tied
 * to the field, and a quiet count of what is left when there is a limit.
 */
export function TextArea({
  label,
  hint,
  error,
  maxChars,
  value,
  ref,
  className,
  rows = 4,
  ...input
}: Readonly<TextAreaProps>) {
  const id = useId();
  const hintId = useId();
  const errorId = useId();
  const countId = useId();
  const invalid = typeof error === 'string' && error !== '';
  const length = Array.from(value ?? '').length;
  const over = maxChars !== undefined && length > maxChars;
  const describedBy = [
    hint === undefined ? null : hintId,
    maxChars === undefined ? null : countId,
    invalid ? errorId : null,
  ]
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
      <textarea
        {...input}
        ref={ref}
        id={id}
        rows={rows}
        value={value}
        aria-invalid={invalid || over || undefined}
        aria-describedby={describedBy === '' ? undefined : describedBy}
        className={cx(
          'w-full resize-y rounded-[14px] border bg-surface px-4 py-3 text-base text-fg leading-[1.8]',
          'transition-[border-color] duration-200 placeholder:text-fg-muted',
          'focus-visible:border-[var(--focus)]',
          invalid || over ? 'border-danger' : 'border-field'
        )}
      />
      {maxChars === undefined ? null : (
        <p
          id={countId}
          className={cx(
            'm-0 text-end text-sm tabular-nums',
            over ? 'text-danger' : 'text-fg-muted'
          )}
        >
          {length} / {maxChars}
        </p>
      )}
      {invalid ? (
        <p id={errorId} className="m-0 text-danger text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
