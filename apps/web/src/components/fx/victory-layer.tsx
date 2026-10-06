'use client';

import { useEffect, useState } from 'react';
import { messages } from '@/messages';
import { VICTORY_EVENT } from './celebrate';
import { KHATAM_RATIO, starPoints } from './geometry';

function Banner() {
  const words = messages.victory.title.split(' ');
  return (
    <div
      className="relative mx-auto flex origin-center flex-col items-center gap-2 py-7 text-center animate-[fx-banner_0.55s_cubic-bezier(0.22,1,0.36,1)_both]"
      style={{ background: 'var(--banner-ground)' }}
    >
      {(['top-0', 'bottom-0'] as const).map((edge, index) => (
        <span
          key={edge}
          aria-hidden="true"
          className={`absolute inset-x-[12%] ${edge} h-px origin-center animate-[fx-banner_0.8s_cubic-bezier(0.22,1,0.36,1)_both]`}
          style={{
            background: 'linear-gradient(90deg, transparent, var(--glow-gold), transparent)',
            animationDelay: `${0.2 + index * 0.1}s`,
          }}
        />
      ))}
      <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <polygon
          points={starPoints(12, 12, 11, 11 * KHATAM_RATIO)}
          style={{ fill: 'var(--glow-gold)' }}
        />
      </svg>
      <p className="m-0 font-bold font-display text-[2.5rem] leading-[1.3] tablet:text-5xl">
        {words.map((word, index) => (
          <span
            key={word}
            className="fx-shimmer inline-block animate-[fx-pop_0.6s_cubic-bezier(0.22,1,0.36,1)_both]"
            style={{ animationDelay: `${0.35 + index * 0.12}s` }}
          >
            {word}
            {index < words.length - 1 ? ' ' : null}
          </span>
        ))}
      </p>
    </div>
  );
}

/**
 * The "battle won" banner of the done button: a band of light opens across the screen,
 * two gold hairlines draw through it and "meaning discovered" pops in word by
 * word, then it leaves on its own. The status region is always there, so the
 * title is announced once each time.
 */
export function VictoryLayer({ duration = 2200 }: Readonly<{ duration?: number }>) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const onVictory = () => setShown((count) => count + 1);
    window.addEventListener(VICTORY_EVENT, onVictory);
    return () => window.removeEventListener(VICTORY_EVENT, onVictory);
  }, []);

  useEffect(() => {
    if (shown === 0) {
      return;
    }
    const timer = window.setTimeout(() => setShown(0), duration);
    return () => window.clearTimeout(timer);
  }, [shown, duration]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-1/2 z-[60] -translate-y-1/2"
    >
      {shown === 0 ? null : <Banner key={shown} />}
    </div>
  );
}
