'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { useIdleHint } from '@/components/scene/use-idle-hint';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/**
 * After the entrance, the mark only breathes: a short shine when the reader has
 * been still for a while, three times at most a page load, as a game's title
 * screen keeps its logo alive without replaying its intro.
 */
export const SHINE_TIMING = { idleMs: 45_000, hintMs: 2_000, max: 3 } as const;

/** Where the sparks rise from around the mark, and when (fx.css «logo entrance»). */
const SPARKS = [
  { left: '18%', top: '30%', delay: '1150ms' },
  { left: '78%', top: '22%', delay: '1250ms' },
  { left: '64%', top: '82%', delay: '1350ms' },
  { left: '30%', top: '76%', delay: '1450ms' },
] as const;

/**
 * The designer's mark, leading home; its accessible name is the product's name.
 * On a page load it is written in stroke by stroke, a ring of light opens behind
 * it and a few sparks rise, once (fx.css «logo entrance»); after that only its shine
 * returns, when the reader has been still for a while.
 */
export function Brand({ className }: Readonly<{ className?: string }>) {
  const idle = useIdleHint(true, SHINE_TIMING);
  const [shine, setShine] = useState(0);
  useEffect(() => {
    if (idle) {
      setShine((count) => count + 1);
    }
  }, [idle]);
  return (
    <Link
      href="/"
      className={cx(
        'relative inline-flex min-h-12 shrink-0 items-center rounded-full px-1',
        className
      )}
    >
      <span aria-hidden="true" className="pointer-events-none absolute inset-0">
        <span className="fx-logo-flare absolute inset-[-30%] rounded-full" />
        <span className="fx-logo-ring absolute inset-[-6%] rounded-full border border-[var(--glow-gold)]" />
        {SPARKS.map((spark) => (
          <span
            key={spark.delay}
            className="fx-logo-spark absolute size-1 rounded-full bg-[var(--glow-gold)]"
            style={{ left: spark.left, top: spark.top, animationDelay: spark.delay }}
          />
        ))}
      </span>
      <LogoMark title={messages.brand.name} className="relative h-12" entrance shine={shine} />
    </Link>
  );
}
