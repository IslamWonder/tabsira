'use client';

import { useEffect, useState } from 'react';
import { motionAllowed } from '@/preferences/motion';

const FORMAT = new Intl.NumberFormat('ar-u-nu-arab');

function easeOut(t: number): number {
  return 1 - (1 - t) ** 3;
}

/**
 * A number that rolls up to its value once shown (an odometer), in Arabic
 * digits. The final value is rendered first, so the server and screen readers
 * get the truth; the roll only plays when decorative motion is allowed. For
 * real counts only: never a score of a person (GAMIFICATION.md §0).
 */
export function CountUp({
  value,
  duration = 1.1,
  className,
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (!motionAllowed()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / (duration * 1000));
      setShown(Math.round(value * easeOut(t)));
      if (t < 1) {
        frame = requestAnimationFrame(tick);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return <span className={className}>{FORMAT.format(shown)}</span>;
}
