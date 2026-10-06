'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LogoMark } from '@/components/brand/logo';
import { LogoLight } from '@/components/brand/logo-light';
import { useIdleHint } from '@/components/scene/use-idle-hint';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/**
 * After the entrance, the mark only breathes: a short shine when the reader has
 * been still for a while, three times at most a page load, as a game's title
 * screen keeps its logo alive without replaying its intro.
 */
export const SHINE_TIMING = { idleMs: 45_000, hintMs: 2_000, max: 3 } as const;

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
      <LogoLight />
      <LogoMark title={messages.brand.name} className="relative h-12" entrance shine={shine} />
    </Link>
  );
}
