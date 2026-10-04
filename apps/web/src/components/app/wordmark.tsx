import { cx } from '@/lib/cx';
import { ar } from '@/messages/ar';

export interface WordmarkProps {
  /** Gilded in the top bar beside the star mark; plain over a photo. */
  tone?: 'plain' | 'gilded';
  className?: string;
}

/**
 * The name in Reem Kufi with its gold point, as drawn in direction C. A
 * placeholder for the designer's logo, which will replace it.
 */
export function Wordmark({ tone = 'plain', className }: WordmarkProps) {
  return (
    <span
      className={cx(
        'font-heading font-bold leading-none',
        tone === 'gilded' ? 'text-gilded' : 'text-fg',
        className
      )}
    >
      {ar.brand.wordmark}
      <span aria-hidden="true" className="text-quran [-webkit-text-fill-color:currentColor]">
        .
      </span>
    </span>
  );
}
