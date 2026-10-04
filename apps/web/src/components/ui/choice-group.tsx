'use client';

import { type ReactNode, useId } from 'react';
import { CheckIcon } from '@/components/icons';
import { cx } from '@/lib/cx';

export interface Choice<T extends string> {
  value: T;
  label: string;
}

interface GroupProps {
  legend: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}

/*
 * Answers as chips: native radio buttons or checkboxes under the chips, so
 * arrow keys, Space and screen readers work as everywhere else (Jakob's law),
 * and every chip is a 48 px target. The chosen one is filled and carries a
 * check mark, not colour alone (Law of Similarity).
 */
const CHIP =
  'relative inline-flex min-h-12 cursor-pointer items-center gap-2 rounded-full border px-4 text-[0.9375rem] ' +
  'transition-[background-color,color,border-color] duration-200 ' +
  'has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2 ' +
  'has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60';
const ON = 'fill-primary border-transparent font-semibold';
const OFF = 'border-line bg-surface text-fg-soft hover:text-fg';

function Mark({ on }: { on: boolean }) {
  return (
    <span className="inline-flex w-4 justify-center">
      {on ? <CheckIcon width="16" height="16" /> : null}
    </span>
  );
}

function Frame({ legend, hint, className, children }: GroupProps & { children: ReactNode }) {
  const hintId = useId();
  return (
    <fieldset
      className={cx('m-0 flex min-w-0 flex-col gap-2 border-0 p-0', className)}
      aria-describedby={hint === undefined ? undefined : hintId}
    >
      <legend className="mb-1 p-0 font-semibold text-fg text-lg">{legend}</legend>
      {hint === undefined ? null : (
        <p id={hintId} className="m-0 text-fg-muted text-sm">
          {hint}
        </p>
      )}
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

/** One answer of several (a radio group). */
export function ChoiceGroup<T extends string>({
  options,
  value,
  onChange,
  disabled,
  ...frame
}: GroupProps & { options: readonly Choice<T>[]; value: T; onChange: (value: T) => void }) {
  const name = useId();
  return (
    <Frame {...frame}>
      {options.map((option) => {
        const on = option.value === value;
        return (
          <label key={option.value} className={cx(CHIP, on ? ON : OFF)}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={on}
              disabled={disabled}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <Mark on={on} />
            {option.label}
          </label>
        );
      })}
    </Frame>
  );
}

/** Any number of answers, none included (checkboxes). */
export function ChoiceChecks<T extends string>({
  options,
  values,
  onChange,
  disabled,
  ...frame
}: GroupProps & {
  options: readonly Choice<T>[];
  values: readonly T[];
  onChange: (values: T[]) => void;
}) {
  return (
    <Frame {...frame}>
      {options.map((option) => {
        const on = values.includes(option.value);
        return (
          <label key={option.value} className={cx(CHIP, on ? ON : OFF)}>
            <input
              type="checkbox"
              value={option.value}
              checked={on}
              disabled={disabled}
              onChange={() =>
                onChange(
                  on
                    ? values.filter((item) => item !== option.value)
                    : options
                        .map((item) => item.value)
                        .filter((item) => item === option.value || values.includes(item))
                )
              }
              className="sr-only"
            />
            <Mark on={on} />
            {option.label}
          </label>
        );
      })}
    </Frame>
  );
}
