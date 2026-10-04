'use client';

import { useId } from 'react';
import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';
import { setAmbientMotion, useAmbientMotion } from '@/preferences/motion';

/**
 * On or off for decorative motion, as a real switch (role="switch", Space and
 * Enter toggle it). The thumb slides when pressed, which is motion on an
 * event, and stops sliding when motion is off.
 */
export function MotionSwitch({ className }: { className?: string }) {
  const on = useAmbientMotion();
  const labelId = useId();
  const hintId = useId();
  return (
    <div className={cx('flex items-start justify-between gap-4', className)}>
      <div className="flex flex-col gap-1">
        <p id={labelId} className="m-0 font-heading font-semibold text-fg text-lg">
          {ar.preferences.motion.label}
        </p>
        <p id={hintId} className="m-0 text-fg-muted text-sm">
          {ar.preferences.motion.hint}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-labelledby={labelId}
        aria-describedby={hintId}
        onClick={() => setAmbientMotion(!on)}
        className="flex min-h-12 shrink-0 items-center rounded-full px-1"
      >
        <span
          className={cx(
            'flex h-8 w-14 items-center rounded-full border p-1 transition-colors duration-200',
            on
              ? 'fill-primary justify-end border-transparent'
              : 'justify-start border-line bg-surface'
          )}
        >
          <span
            aria-hidden="true"
            className={cx(
              'size-6 rounded-full shadow',
              on ? 'bg-[var(--on-primary)]' : 'bg-[var(--text-muted)]'
            )}
          />
        </span>
      </button>
    </div>
  );
}
