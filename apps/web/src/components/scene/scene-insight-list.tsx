'use client';

import { useId } from 'react';
import type { ScenePoint } from '@/components/insight/scene-photo';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export interface SceneInsightListProps {
  points: readonly ScenePoint[];
  selectedId?: string;
  onSelect: (id: string) => void;
}

/**
 * The photo's insights as a visible list in the panel, from tablet up: the
 * screen-reader list made a feature (DESIGN_DECISION.md). Each row carries the
 * point's own glow colour so the eye links it to the photo (Law of
 * Similarity), and the list keeps the order of the points (Serial position).
 */
export function SceneInsightList({ points, selectedId, onSelect }: SceneInsightListProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="m-0 font-semibold text-subheading text-fg">
        {messages.scene.hint}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {points.map((point) => {
          const gold = point.tone !== 'emerald';
          return (
            <li key={point.id}>
              <button
                type="button"
                onClick={() => onSelect(point.id)}
                aria-current={point.id === selectedId ? 'true' : undefined}
                className={cx(
                  'flex min-h-[76px] w-full items-center gap-3.5 rounded-[18px] border px-[18px] py-3 text-start transition-colors duration-200',
                  gold
                    ? 'border-[var(--quran-border)] bg-[var(--quran-surface-from)] hover:bg-[var(--quran-surface-to)]'
                    : 'border-[var(--sunnah-border)] bg-[var(--sunnah-surface-from)] hover:bg-[var(--sunnah-surface-to)]',
                  point.id === selectedId && 'outline-2 outline-[var(--focus)]'
                )}
              >
                <span
                  aria-hidden="true"
                  className="size-3.5 shrink-0 rounded-full"
                  style={{
                    background: gold ? 'var(--point-gold-core)' : 'var(--point-emerald-core)',
                    boxShadow: `0 0 12px 4px ${gold ? 'var(--point-gold-halo)' : 'var(--point-emerald-halo)'}`,
                  }}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="font-semibold text-fg text-lg">{point.title}</span>
                  {point.glimpse === undefined ? null : (
                    <>
                      {' '}
                      <span className="text-fg-soft text-sm">{point.glimpse}</span>
                    </>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
