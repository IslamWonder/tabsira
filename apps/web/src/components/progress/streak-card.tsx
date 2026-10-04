import { CheckIcon } from '@/components/icons';
import { GlassPanel } from '@/components/ui/glass-panel';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import type { Progress } from '@/progress/api';

const M = messages.practiceView.streak;

/** The day of the month from an ISO date, with no time zone arithmetic: «2026-10-04» is the 4th. */
function dayOfMonth(day: string): number {
  return Number(day.slice(8, 10));
}

/**
 * The streak of looking days and the last seven days as a row of lanterns,
 * today first. Quiet by design: no loss warning when it breaks, no pressure
 * (owner decision 27).
 */
export function StreakCard({ streak }: { streak: Progress['streak'] }) {
  return (
    <GlassPanel as="section" aria-labelledby="practice-streak" className="flex flex-col gap-3">
      <p className="m-0 text-[var(--step-title)] text-sm">{M.label}</p>
      <h2
        id="practice-streak"
        className="m-0 font-bold font-display text-[1.5rem] text-fg leading-[1.3]"
      >
        {M.current(streak.current)}
      </h2>
      <p className="m-0 text-fg-muted text-sm">{M.best(streak.best)}</p>
      <ol aria-label={M.week} className="m-0 flex list-none justify-between gap-1 p-0">
        {streak.days.map((entry, index) => (
          <li key={entry.day} className="flex flex-col items-center gap-1">
            <span
              className={cx(
                'flex size-10 items-center justify-center rounded-full border',
                entry.looked
                  ? 'border-[var(--quran-border)] bg-[var(--chip-primary-bg)] text-primary'
                  : 'border-line text-fg-muted'
              )}
            >
              {entry.looked ? <CheckIcon width="18" height="18" /> : dayOfMonth(entry.day)}
            </span>
            <span className="text-fg-muted text-xs">
              {index === 0 ? M.today : dayOfMonth(entry.day)}
              <span className="sr-only"> {entry.looked ? M.looked : M.notLooked}</span>
            </span>
          </li>
        ))}
      </ol>
    </GlassPanel>
  );
}
