import { QuestLog } from '@/components/fx/quest-log';
import { StageOrbit } from '@/components/fx/stage-orbit';
import { Button } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';

export const STAGES = ['scene', 'evidence', 'verify', 'compose'] as const;
export type StageId = (typeof STAGES)[number];
export type StageState = 'done' | 'current' | 'pending';

export interface ProgressStagesProps {
  /** The stage the server reports as running, or `done` once the insight is ready. */
  current: StageId | 'done';
  /** The request is taking longer than usual: say so calmly (tajriba §8). */
  slow?: boolean;
  /** Leaves the wait; the late answer must then be ignored by the caller. */
  onCancel?: () => void;
  className?: string;
}

export function stageState(stage: StageId, current: StageId | 'done'): StageState {
  if (current === 'done') {
    return 'done';
  }
  const at = STAGES.indexOf(stage);
  const now = STAGES.indexOf(current);
  if (at < now) {
    return 'done';
  }
  return at === now ? 'current' : 'pending';
}

/**
 * The four real stages of preparing an insight, as the server reports them.
 * No percentage and no countdown (tajriba §8): a quarter of the ring lights up
 * when a stage is done, which is all the system actually knows. Seeing the
 * whole path and how much of it is behind keeps the wait bearable
 * (Goal-gradient effect); the stage names say what is happening (Doherty
 * threshold: feedback even when the answer itself takes longer).
 *
 * From tablet up: the orbit beside a quest log of the four stages. On a phone:
 * one compact line of four segments under the current stage's name.
 */
export function ProgressStages({
  current,
  slow = false,
  onCancel,
  className,
}: ProgressStagesProps) {
  const done = current === 'done';
  const label = done ? ar.progress.complete : ar.progress.stages[current];
  const states = STAGES.map((stage) => stageState(stage, current));

  return (
    <section
      aria-label={ar.progress.label}
      className={cx(
        'flex flex-col gap-4 tablet:flex-row tablet:items-center tablet:gap-10',
        className
      )}
    >
      <StageOrbit states={states} className="hidden tablet:block" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div role="status" aria-live="polite" aria-atomic="true" className="flex flex-col gap-1">
          <p
            key={current}
            className="m-0 font-heading font-semibold text-fg text-xl motion-safe:animate-fade-in"
          >
            {label}
          </p>
          {slow && !done ? (
            <p className="m-0 max-w-sm text-fg-soft text-sm">{ar.progress.slow}</p>
          ) : null}
        </div>
        <QuestLog
          entries={STAGES.map((stage, index) => ({
            key: stage,
            label: ar.progress.stages[stage],
            state: states[index] as StageState,
          }))}
        />
        {onCancel === undefined || done ? null : (
          <div>
            <Button variant="ghost" onClick={onCancel} className="-ms-4">
              {ar.progress.cancel}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
