'use client';

import { useState } from 'react';
import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { LinkButton } from '@/components/ui/button';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import type { Progress, Star } from '@/progress/api';

const M = messages.practiceView.sky;

/** A star grows a little with each time its meaning came back, up to a limit that keeps the sky calm. */
function radius(count: number): number {
  return 7 + Math.min(count - 1, 3) * 1.5;
}

function StarButton({
  star,
  selected,
  onSelect,
}: {
  star: Star;
  selected: boolean;
  onSelect: () => void;
}) {
  const size = radius(star.count);
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={M.star(star.concept, star.count)}
      onClick={onSelect}
      className="absolute flex size-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-transparent p-0"
      // The star's place is a ratio of the sky measured from its left edge, in either reading direction.
      style={{ left: `${star.x * 100}%`, top: `${star.y * 100}%` }}
    >
      <svg
        width="30"
        height="30"
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
        className={cx(selected && 'drop-shadow-[0_0_6px_var(--glow-gold)]')}
      >
        <circle
          cx="12"
          cy="12"
          r={size + 3}
          style={{ fill: 'var(--glow-gold)' }}
          opacity={0.18}
          className="origin-center motion-safe:animate-breathe"
        />
        <polygon
          points={starPoints(12, 12, size, size * KHATAM_RATIO)}
          style={{ fill: 'var(--glow-gold)', stroke: 'var(--ornament)' }}
          strokeWidth={0.7}
        />
      </svg>
    </button>
  );
}

/**
 * The sky of meanings: one star for each meaning that appeared in an insight
 * the learner completed. Its place comes from the meaning's name alone, so it
 * never moves. No lines join the stars: a relation is drawn only where one is
 * recorded, and that is the world's thread, not the sky's.
 */
export function SkyOfMeanings({ sky }: { sky: Progress['sky'] }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const star = sky.stars.find((item) => item.concept === chosen);
  return (
    <GlassPanel as="section" ornate aria-labelledby="practice-sky" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="practice-sky" className="m-0 font-bold font-display text-[1.5rem] text-fg">
          {M.title}
        </h2>
        <span className="text-fg-soft text-sm">{M.count(sky.count)}</span>
      </div>
      {sky.stars.length === 0 ? (
        <div className="flex flex-col items-start gap-3">
          <p className="m-0 text-fg-soft leading-[1.9]">{M.empty}</p>
          <LinkButton href="/" variant="secondary">
            {M.cta}
          </LinkButton>
        </div>
      ) : (
        <>
          <fieldset className="stage-aurora relative m-0 aspect-[5/3] w-full min-w-0 overflow-hidden rounded-[var(--radius-card)] border border-line p-0">
            <legend className="sr-only">{M.label}</legend>
            <div aria-hidden="true" className="stage-stars absolute inset-0" />
            {sky.stars.map((item) => (
              <StarButton
                key={item.concept}
                star={item}
                selected={item.concept === chosen}
                onSelect={() => setChosen(item.concept === chosen ? null : item.concept)}
              />
            ))}
          </fieldset>
          <p aria-live="polite" className="m-0 min-h-6 text-fg text-sm">
            {star ? M.star(star.concept, star.count) : null}
          </p>
        </>
      )}
    </GlassPanel>
  );
}
