'use client';

import { type CSSProperties, useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { SparkIcon } from '@/components/icons';
import type { ScenePoint } from '@/components/insight/scene-photo';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { useIdleHint } from './use-idle-hint';

export interface SceneInsightListProps {
  points: readonly ScenePoint[];
  selectedId?: string;
  onSelect: (id: string) => void;
  /**
   * The insights were just found and wait to be chosen: the rows call once
   * when they show, and a short hint comes after a while without a tap.
   */
  invite?: boolean;
}

/** The hint of an idle reader: a toast above the navigation, so nothing in the page moves. */
function ChooseHint({ shown }: { shown: boolean }) {
  if (typeof document === 'undefined') {
    return null;
  }
  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(var(--nav-clearance)+12px)] z-40 flex justify-center px-4 tablet:bottom-8"
    >
      {shown ? (
        <p className="fx-enter glass m-0 inline-flex items-center gap-2 rounded-full px-4 py-2.5 font-semibold text-fg text-sm shadow-[var(--panel-shadow)]">
          <SparkIcon width="18" height="18" className="text-[var(--glow-gold)]" />
          {messages.scene.chooseHint}
        </p>
      ) : null}
    </div>,
    document.body
  );
}

/**
 * The photo's insights as a visible list in the panel, from tablet up: the
 * screen-reader list made a feature (DESIGN_DECISION.md). Each row carries the
 * point's own glow colour so the eye links it to the photo (Law of
 * Similarity), and the list keeps the order of the points (Serial position).
 * Fresh from an analysis it invites the choice: a gold sheen crosses each row
 * and a ring leaves its dot, one row after the other, twice (motion on display,
 * never on hover; still under reduced motion), and an idle reader gets a hint.
 */
export function SceneInsightList({
  points,
  selectedId,
  onSelect,
  invite = false,
}: Readonly<SceneInsightListProps>) {
  const headingId = useId();
  const hint = useIdleHint(invite);
  // Each showing of the hint replays the rows' call, so the words and the rows go together.
  const [calls, setCalls] = useState(0);
  useEffect(() => {
    if (hint) {
      setCalls((count) => count + 1);
    }
  }, [hint]);
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="m-0 font-semibold text-subheading text-fg">
        {messages.scene.hint}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {points.map((point, index) => {
          const gold = point.tone !== 'emerald';
          const call = { '--fx-delay': `${400 + index * 280}ms` } as CSSProperties;
          return (
            <li key={point.id}>
              <button
                type="button"
                onClick={() => onSelect(point.id)}
                aria-current={point.id === selectedId ? 'true' : undefined}
                className={cx(
                  'relative flex min-h-[76px] w-full items-center gap-3.5 rounded-[18px] border px-[18px] py-3 text-start transition-colors duration-200',
                  gold
                    ? 'border-[var(--quran-border)] bg-[var(--quran-surface-from)] hover:bg-[var(--quran-surface-to)]'
                    : 'border-[var(--sunnah-border)] bg-[var(--sunnah-surface-from)] hover:bg-[var(--sunnah-surface-to)]',
                  point.id === selectedId && 'outline-2 outline-[var(--focus)]'
                )}
              >
                {invite ? (
                  <span key={calls} aria-hidden="true" className="fx-sheen" style={call} />
                ) : null}
                <span
                  aria-hidden="true"
                  className="relative size-3.5 shrink-0 rounded-full"
                  style={{
                    background: gold ? 'var(--point-gold-core)' : 'var(--point-emerald-core)',
                    boxShadow: `0 0 12px 4px ${gold ? 'var(--point-gold-halo)' : 'var(--point-emerald-halo)'}`,
                  }}
                >
                  {invite ? (
                    <span
                      key={calls}
                      className="fx-dot-ring absolute -inset-1 rounded-full border-2"
                      style={{
                        ...call,
                        borderColor: gold ? 'var(--point-gold-halo)' : 'var(--point-emerald-halo)',
                      }}
                    />
                  ) : null}
                </span>
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
      {invite ? <ChooseHint shown={hint} /> : null}
    </section>
  );
}
