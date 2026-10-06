'use client';

import { type ReactNode, useId } from 'react';

export interface SwitchFieldProps {
  /** The form field's name: the switch is a real checkbox, so a form posts it without JavaScript. */
  name: string;
  label: string;
  hint?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/**
 * An on/off choice inside a form: a native checkbox with role="switch" (Space
 * toggles it, screen readers say "switch, on"), drawn like SwitchRow so every
 * switch of the app looks the same (Law of Similarity). It works before the
 * page's scripts arrive, posted with its form.
 */
export function SwitchField({
  name,
  label,
  hint,
  checked,
  onChange,
  disabled,
}: Readonly<SwitchFieldProps>) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <label htmlFor={id} className="font-semibold text-fg text-lg">
          {label}
        </label>
        {hint === undefined ? null : (
          <p id={hintId} className="m-0 text-fg-muted text-sm leading-[1.8]">
            {hint}
          </p>
        )}
      </div>
      <span className="relative flex min-h-12 shrink-0 items-center px-1">
        <input
          id={id}
          type="checkbox"
          role="switch"
          name={name}
          checked={checked}
          aria-checked={checked}
          disabled={disabled}
          aria-describedby={hint === undefined ? undefined : hintId}
          onChange={(event) => onChange(event.target.checked)}
          className="peer absolute inset-0 z-10 size-full cursor-pointer appearance-none rounded-full disabled:cursor-not-allowed"
        />
        <span
          aria-hidden="true"
          className="flex h-8 w-14 items-center justify-start rounded-full border border-field bg-surface p-1 transition-colors duration-200 peer-checked:justify-end peer-checked:border-transparent peer-checked:bg-[var(--primary-fill-to)] peer-focus-visible:outline-3 peer-focus-visible:outline-[var(--focus)] peer-focus-visible:outline-offset-2 peer-disabled:opacity-60"
        >
          <span className="size-6 rounded-full bg-[var(--text-muted)] shadow [.peer:checked~*_&]:bg-[var(--on-primary)]" />
        </span>
      </span>
    </div>
  );
}
