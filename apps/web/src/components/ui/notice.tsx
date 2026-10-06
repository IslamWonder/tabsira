import type { ReactNode } from 'react';
import { CheckIcon } from '@/components/icons';
import { cx } from '@/lib/cx';

export type NoticeTone = 'error' | 'success' | 'info';

const TONES: Record<NoticeTone, string> = {
  error: 'border-danger text-danger',
  success: 'border-[var(--chip-primary-border)] text-fg',
  info: 'border-line text-fg-soft',
};

export interface NoticeProps {
  tone: NoticeTone;
  className?: string;
  children: ReactNode;
}

/**
 * A short message about what just happened, next to where it happened (tajriba
 * §3.5: success after it is confirmed, failure with a way to fix it). Text and
 * a mark carry the state, never colour alone (Law of Similarity). The caller
 * puts it inside a live region (role="status" or "alert") that already exists
 * when the message arrives, so screen readers announce it.
 */
export function Notice({ tone, className, children }: Readonly<NoticeProps>) {
  return (
    <div
      className={cx(
        'flex items-start gap-2.5 rounded-[14px] border bg-surface px-4 py-3 text-[0.9375rem] leading-[1.8]',
        TONES[tone],
        className
      )}
    >
      {tone === 'success' ? (
        <CheckIcon width="20" height="20" className="mt-1 shrink-0 text-primary" />
      ) : (
        <span
          aria-hidden="true"
          className={cx(
            'mt-[0.7rem] size-2 shrink-0 rounded-full',
            tone === 'error' ? 'bg-danger' : 'bg-[var(--text-muted)]'
          )}
        />
      )}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
