import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { cx } from '@/lib/cx';

/**
 * The world's growth, shown where it is said: a khatam star at the new place,
 * with a veil of fog that lifts from it once (the fog lifting after the done action,
 * DESIGN_DECISION.md). The veil only plays for a place made by this
 * completion, and only on display; the star is there either way, and the
 * place's name beside it says the same in words.
 */
export function PlaceReveal({ created, className }: { created: boolean; className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-place={created ? 'new' : 'known'}
      className={cx('relative inline-flex size-14 shrink-0 items-center justify-center', className)}
    >
      <svg width="40" height="40" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <polygon
          points={starPoints(12, 12, 11, 11 * KHATAM_RATIO)}
          style={{ fill: 'var(--glow-gold)' }}
        />
      </svg>
      {created ? (
        <span
          data-mist
          className="pointer-events-none absolute inset-0 rounded-full motion-safe:animate-[fx-mist_1.8s_cubic-bezier(0.22,1,0.36,1)_0.3s_both]"
          style={{ background: 'radial-gradient(circle, var(--bg) 35%, transparent 72%)' }}
        />
      ) : null}
    </span>
  );
}
