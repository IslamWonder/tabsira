import { SparkIcon } from '@/components/icons';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/**
 * The fixed AI disclosure (master prompt §12), shown on the result and in the
 * chat. Quiet, but never hidden behind a tap.
 */
export function DisclosureLine({ className }: Readonly<{ className?: string }>) {
  return (
    <p
      className={cx(
        'm-0 flex items-center justify-center gap-1.5 text-center text-[0.8125rem] text-fg-muted leading-relaxed',
        className
      )}
    >
      <SparkIcon width="15" height="15" className="shrink-0" />
      {messages.disclosure.ai}
    </p>
  );
}
