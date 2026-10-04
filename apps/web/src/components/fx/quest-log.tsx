import { CheckIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export type QuestState = 'done' | 'current' | 'pending';

export interface QuestEntry {
  key: string;
  label: string;
  state: QuestState;
}

/**
 * The "objective updated" log of an RPG, for real steps only: finished ones
 * get a gold check that draws itself, the current one a pulsing diamond, the
 * rest a hollow one. The whole path stays visible (Goal-gradient effect). On a
 * phone it folds into one compact line of segments, the names kept for screen
 * readers.
 */
export function QuestLog({
  entries,
  className,
}: {
  entries: readonly QuestEntry[];
  className?: string;
}) {
  return (
    <ol
      className={cx(
        'm-0 grid list-none grid-cols-4 gap-1.5 p-0 tablet:flex tablet:flex-col tablet:gap-2.5',
        className
      )}
    >
      {entries.map(({ key, label, state }) => (
        <li
          key={key}
          aria-current={state === 'current' ? 'step' : undefined}
          className={cx(
            'flex items-center gap-2.5 text-[0.9375rem]',
            state === 'done' && 'text-fg-soft',
            state === 'current' && 'font-semibold text-fg',
            state === 'pending' && 'text-fg-muted'
          )}
        >
          {/* Phone: one segment of the compact line. */}
          <span
            aria-hidden="true"
            className={cx(
              'h-1.5 w-full rounded-full tablet:hidden',
              state === 'done' && 'bg-[var(--glow-gold)]',
              state === 'current' && 'bg-[var(--glow-gold)] motion-safe:animate-pulse-soft',
              state === 'pending' && 'bg-[var(--border)]'
            )}
          />
          {/* Tablet and up: the log's marker. */}
          <span
            aria-hidden="true"
            className="hidden size-6 shrink-0 items-center justify-center tablet:inline-flex"
          >
            {state === 'done' ? (
              <span className="flex size-6 items-center justify-center rounded-full border border-[var(--quran-border)] bg-[var(--chip-primary-bg)] text-primary">
                <CheckIcon
                  width="14"
                  height="14"
                  className="[stroke-dasharray:24] motion-safe:animate-draw"
                />
              </span>
            ) : (
              <span
                className={cx(
                  'size-2.5 rotate-45',
                  state === 'current'
                    ? 'bg-[var(--glow-gold)] shadow-[0_0_10px_var(--glow-gold)] motion-safe:animate-pulse-soft'
                    : 'border border-[var(--text-muted)]'
                )}
              />
            )}
          </span>
          <span className="sr-only tablet:not-sr-only">
            {label}
            <span className="sr-only"> {messages.progress.status[state]}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
