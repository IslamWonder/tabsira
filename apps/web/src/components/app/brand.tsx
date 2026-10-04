import Link from 'next/link';
import { LogoMark } from '@/components/brand/logo';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

/** The designer's mark, leading home; its accessible name is the product's name. */
export function Brand({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cx('inline-flex min-h-12 shrink-0 items-center rounded-full px-1', className)}
    >
      <LogoMark title={messages.brand.name} className="h-12" />
    </Link>
  );
}
