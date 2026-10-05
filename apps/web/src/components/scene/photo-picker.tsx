'use client';

import { type ChangeEvent, type ReactNode, useId } from 'react';
import { cx } from '@/lib/cx';

export interface PhotoPickerProps {
  onPick: (event: ChangeEvent<HTMLInputElement>) => void;
  /** `environment` asks a phone for its back camera app instead of the gallery. */
  capture?: 'environment';
  /** The look of the control; the focus ring is added here. */
  className: string;
  /** The visible name of the control, an icon beside it if any. */
  children: ReactNode;
}

/**
 * The device's own photo picker dressed as a button: a label holding a hidden
 * file input, so the input keeps its native behaviour (and its name, the
 * label's text) and the ring shows when it has keyboard focus.
 */
export function PhotoPicker({ onPick, capture, className, children }: PhotoPickerProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={cx(
        'cursor-pointer has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2',
        className
      )}
    >
      {children}
      <input
        id={id}
        type="file"
        accept="image/*"
        capture={capture}
        className="sr-only"
        onChange={onPick}
      />
    </label>
  );
}
