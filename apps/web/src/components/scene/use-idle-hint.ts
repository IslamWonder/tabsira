'use client';

import { useEffect, useState } from 'react';

/** Milliseconds without a tap, a key or a scroll before the hint shows. */
export const IDLE_MS = 7000;
/** Milliseconds the hint stays before it goes by itself. */
export const HINT_MS = 6000;
/** A hint is a reminder, not a nag: it comes back once at most. */
export const MAX_HINTS = 2;

/** Another wait, length or count than the scan hint's, for another reminder. */
export interface IdleTiming {
  idleMs?: number;
  hintMs?: number;
  max?: number;
}

const ACTIVITY = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'] as const;

/**
 * True while a short hint should show: after IDLE_MS with no sign of the
 * reader, for HINT_MS, at most MAX_HINTS times (or the timing given). Any tap, key or scroll hides it
 * and starts the wait again; the reader who is reading or choosing is never
 * interrupted.
 */
export function useIdleHint(
  enabled: boolean,
  { idleMs = IDLE_MS, hintMs = HINT_MS, max = MAX_HINTS }: IdleTiming = {}
): boolean {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setShown(false);
      return;
    }
    let count = 0;
    let idle: ReturnType<typeof setTimeout> | undefined;
    let hide: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      clearTimeout(idle);
      if (count >= max) {
        return;
      }
      idle = setTimeout(() => {
        count += 1;
        setShown(true);
        hide = setTimeout(() => {
          setShown(false);
          arm();
        }, hintMs);
      }, idleMs);
    };
    const active = () => {
      clearTimeout(hide);
      setShown(false);
      arm();
    };
    for (const name of ACTIVITY) {
      window.addEventListener(name, active, { passive: true, capture: true });
    }
    arm();
    return () => {
      clearTimeout(idle);
      clearTimeout(hide);
      for (const name of ACTIVITY) {
        window.removeEventListener(name, active, { capture: true });
      }
    };
  }, [enabled, idleMs, hintMs, max]);

  return shown;
}
