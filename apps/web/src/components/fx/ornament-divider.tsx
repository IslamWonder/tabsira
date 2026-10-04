import { cx } from '@/lib/cx';
import { KHATAM_RATIO, starPoints } from './geometry';

function Rosette() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
    >
      <polygon
        points={starPoints(12, 12, 10.5, 10.5 * KHATAM_RATIO)}
        fill="none"
        stroke="currentColor"
        strokeWidth={0.9}
        strokeLinejoin="round"
      />
      <polygon points={starPoints(12, 12, 5.2, 5.2 * KHATAM_RATIO)} fill="currentColor" />
    </svg>
  );
}

/**
 * A hairline that fades in from both ends toward a gold rosette (Law of
 * Common Region by separation: it ends one group and opens the next). With a
 * label, the words sit between two rosettes. Decorative: the label is the only
 * part read aloud.
 */
export function OrnamentDivider({ label, className }: { label?: string; className?: string }) {
  const line = (direction: 'right' | 'left') => (
    <span
      aria-hidden="true"
      className="h-px min-w-2 flex-1 opacity-60"
      style={{ background: `linear-gradient(to ${direction}, transparent, currentColor)` }}
    />
  );
  return (
    <div className={cx('flex w-full items-center gap-3 text-[var(--ornament)]', className)}>
      {line('left')}
      <Rosette />
      {label === undefined ? null : (
        <>
          <span className="font-semibold text-fg-soft text-sm">{label}</span>
          <Rosette />
        </>
      )}
      {line('right')}
    </div>
  );
}
