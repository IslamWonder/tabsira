import type { ReactNode } from 'react';
import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';

/** The thin gold thread that joins the two sources: what brings them together. */
function Thread() {
  return (
    <svg
      width="24"
      height="40"
      viewBox="0 0 24 40"
      aria-hidden="true"
      focusable="false"
      className="mx-auto block"
    >
      <path
        className="fx-draw"
        pathLength={1}
        d="M12 0V40"
        fill="none"
        style={{ stroke: 'var(--glow-gold)', animationDelay: '0.65s' }}
        strokeWidth={1.25}
        strokeLinecap="round"
      />
      <polygon
        points={starPoints(12, 20, 6, 6 * KHATAM_RATIO)}
        style={{ fill: 'var(--glow-gold)' }}
        className="origin-center motion-safe:animate-[fx-pop_0.5s_cubic-bezier(0.22,1,0.36,1)_0.9s_both]"
      />
    </svg>
  );
}

/**
 * The evidence reveal (DESIGN_DECISION.md «Game feel»): the Quran panel
 * enters from the start side, the Sunnah panel from the end side, and a gold
 * thread draws between them. Only the panels move, once, on display; the
 * scripture inside never animates, glows or shifts. With one source (the
 * hadith still awaiting its ruling), the Quran panel stands alone; likewise a
 * hadith whose verse is not shown.
 */
export function EvidencePair({
  quran,
  sunnah,
  sideBySide = false,
}: {
  quran?: ReactNode;
  sunnah?: ReactNode;
  /**
   * Both texts are short (under about 280 characters): from 1440 px they may
   * sit side by side. Long texts always stack (tajriba §6).
   */
  sideBySide?: boolean;
}) {
  return (
    <div
      className={
        sideBySide
          ? 'flex flex-col wide:grid wide:grid-cols-[1fr_auto_1fr] wide:items-stretch'
          : 'flex flex-col'
      }
    >
      {quran === undefined ? null : (
        <div className="motion-safe:animate-[fx-from-start_0.7s_cubic-bezier(0.22,1,0.36,1)_both]">
          {quran}
        </div>
      )}
      {sunnah === undefined ? null : (
        <>
          {/* A thread joins two sources, never one. */}
          {quran === undefined ? null : <Thread />}
          <div className="motion-safe:animate-[fx-from-end_0.7s_cubic-bezier(0.22,1,0.36,1)_0.12s_both]">
            {sunnah}
          </div>
        </>
      )}
    </div>
  );
}
