import Link from 'next/link';
import { cx } from '@/lib/cx';
import { StarMark } from './star-mark';
import { Wordmark } from './wordmark';

/** The star mark beside the gilded wordmark, leading home. */
export function Brand({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cx(
        'inline-flex min-h-12 shrink-0 items-center gap-3 rounded-full pe-1',
        className
      )}
    >
      <StarMark />
      <Wordmark tone="gilded" className="pt-1 text-[1.75rem]" />
    </Link>
  );
}
