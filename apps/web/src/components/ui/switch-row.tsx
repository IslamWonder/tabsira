'use client';

import { type ReactNode, useId } from 'react';
import { cx } from '@/lib/cx';

export interface SwitchRowProps {
  label: string;
  /** What turning it on or off does, read with the switch. */
  hint?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Unavailable, with the reason in the hint (an under-13 photo choice, a necessary cookie). */
  disabled?: boolean;
  /** A change is being saved: the switch waits, and says so to assistive technology. */
  busy?: boolean;
  className?: string;
}

/**
 * An on/off choice as a real switch (role="switch"; Space and Enter toggle it),
 * with its label and its consequence beside it. One look for every switch in
 * the app (Law of Similarity). The thumb slides when pressed, motion on an
 * event, and stops sliding when motion is off.
 */
export function SwitchRow({
  label,
  hint,
  checked,
  onChange,
  disabled = false,
  busy = false,
  className,
}: SwitchRowProps) {
  const labelId = useId();
  const hintId = useId();
  return (
    <div className={cx('flex items-start justify-between gap-4', className)}>
      <div className="flex min-w-0 flex-col gap-1">
        <p id={labelId} className="m-0 font-semibold text-fg text-lg">
          {label}
        </p>
        {hint === undefined ? null : (
          <p id={hintId} className="m-0 text-fg-muted text-sm leading-[1.8]">
            {hint}
          </p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={hint === undefined ? undefined : hintId}
        aria-busy={busy || undefined}
        disabled={disabled}
        // While saving, a press waits instead of disabling the button, which would drop the focus.
        onClick={() => {
          if (!busy) {
            onChange(!checked);
          }
        }}
        className="flex min-h-12 shrink-0 items-center rounded-full px-1 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span
          className={cx(
            'flex h-8 w-14 items-center rounded-full border p-1 transition-colors duration-200',
            checked
              ? 'fill-primary justify-end border-transparent'
              : 'justify-start border-line bg-surface'
          )}
        >
          <span
            aria-hidden="true"
            className={cx(
              'size-6 rounded-full shadow',
              checked ? 'bg-[var(--on-primary)]' : 'bg-[var(--text-muted)]'
            )}
          />
        </span>
      </button>
    </div>
  );
}
