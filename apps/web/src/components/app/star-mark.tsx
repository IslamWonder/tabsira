import { cx } from '@/lib/cx';

/**
 * The eight-point star (two squares, the khatam) with a point of light at its
 * heart: the insight point of the scene, set in the oldest ornament of the
 * tradition. Drawn in the mark token, gold on night and deep gold on day.
 * A placeholder for the designer's logo, like the icons it matches.
 */
export function StarMark({ size = 34, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
      className={cx('shrink-0 drop-shadow-[0_0_10px_var(--mark-glow)]', className)}
    >
      <g fill="none" strokeWidth={5} strokeLinejoin="round" style={{ stroke: 'var(--mark)' }}>
        <rect x="21" y="21" width="58" height="58" />
        <rect x="21" y="21" width="58" height="58" transform="rotate(45 50 50)" />
      </g>
      <circle cx="50" cy="50" r="10" style={{ fill: 'var(--mark)' }} />
    </svg>
  );
}
