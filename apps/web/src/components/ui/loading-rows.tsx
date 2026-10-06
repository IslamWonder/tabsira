import { cx } from '@/lib/cx';

/* Fixed keys: the shapes never change order and carry no data. */
const ROWS = ['first', 'second', 'third', 'fourth'] as const;

/**
 * What a list shows while its first page loads: a few empty shapes of the rows
 * to come under a slow gold shine, with the honest words for screen readers.
 * The shapes hold no text and no picture, so no content is implied before it
 * exists (tajriba §8); under reduced motion they stay still.
 */
export function LoadingRows({
  label,
  rows = 3,
  rowClassName = 'h-20',
  className,
}: Readonly<{ label: string; rows?: 1 | 2 | 3 | 4; rowClassName?: string; className?: string }>) {
  return (
    <div role="status" className={cx('flex flex-col gap-3', className)}>
      <span className="sr-only">{label}</span>
      {ROWS.slice(0, rows).map((key) => (
        <div
          key={key}
          aria-hidden="true"
          className={cx('fx-placeholder rounded-[var(--radius-card)]', rowClassName)}
        />
      ))}
    </div>
  );
}
