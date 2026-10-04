import { useId } from 'react';
import { CheckIcon, SeedlingIcon } from '@/components/icons';
import { Button } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';

export type StepStatus = 'idle' | 'saving' | 'saved' | 'deferred';

export interface StepCardProps {
  /** The step itself, from the learning path. */
  body: string;
  /** The reader's own statement, named by what it records (tajriba §7, the rain scene's example). */
  confirmLabel: string;
  onConfirm: () => void;
  onDefer: () => void;
  status?: StepStatus;
  className?: string;
}

const STATUS_TEXT: Record<Exclude<StepStatus, 'idle'>, string> = {
  saving: ar.step.saving,
  saved: ar.step.saved,
  deferred: ar.step.deferred,
};

/**
 * The small step: one thing to live by, with exactly two answers, doing it
 * or putting it off (Hick's law). Putting it off is always visible and never
 * shamed. The statement is recorded only when the reader makes it, and success
 * is announced after it is saved, not before (tajriba §3.5); once answered the
 * buttons leave, so a second tap cannot record it twice.
 */
export function StepCard({
  body,
  confirmLabel,
  onConfirm,
  onDefer,
  status = 'idle',
  className,
}: StepCardProps) {
  const titleId = useId();
  const answered = status === 'saved' || status === 'deferred';
  const saving = status === 'saving';

  return (
    <section
      aria-labelledby={titleId}
      aria-busy={saving}
      className={cx(
        'surface-step flex flex-col gap-3 rounded-[var(--radius-panel)] p-[18px]',
        'tablet:flex-row tablet:items-center tablet:gap-5 tablet:px-[22px]',
        className
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <h2
          id={titleId}
          className="m-0 flex items-center gap-2 font-bold text-[1.0625rem] text-step-title"
        >
          <SeedlingIcon width="20" height="20" />
          {ar.step.title}
        </h2>
        <p className="m-0 text-[0.96875rem] text-fg leading-[1.85]">{body}</p>
        <p role="status" className="m-0 flex min-h-6 items-center gap-2 text-fg-soft text-sm">
          {status === 'saved' ? (
            <CheckIcon width="18" height="18" className="text-primary" />
          ) : null}
          {status === 'idle' ? null : STATUS_TEXT[status]}
        </p>
      </div>
      {answered ? null : (
        // Side by side on a phone; stacked beside the text from tablet up (the horizontal card).
        <div className="flex flex-wrap gap-2.5 tablet:shrink-0 tablet:flex-col tablet:items-stretch tablet:gap-1.5">
          <Button variant="secondary" onClick={onConfirm} disabled={saving}>
            {confirmLabel}
          </Button>
          <Button variant="ghost" onClick={onDefer} disabled={saving}>
            {ar.step.defer}
          </Button>
        </div>
      )}
    </section>
  );
}
