import { useId } from 'react';
import { cx } from '@/lib/cx';
import { KHATAM_RATIO, starPoints } from './geometry';
import type { QuestState } from './quest-log';

const SIZE = 200;
const CENTRE = SIZE / 2;
const ARC = 68;
const GLYPH_RING = 86;

/** One glyph per stage, in order: the eye sees, the star searches, the book verifies, the check prepares. */
const GLYPHS = [
  'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z M12 9.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5Z',
  'M12 3c.6 4.2 2.8 6.4 7 7-4.2.6-6.4 2.8-7 7-.6-4.2-2.8-6.4-7-7 4.2-.6 6.4-2.8 7-7Z',
  'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z',
  'M20 6 9 17l-5-5',
] as const;

/** The point after `index` quarters: from the top, counter-clockwise, as Arabic reads. */
function onRing(index: number, radius: number) {
  const angle = -Math.PI / 2 - (Math.PI / 2) * index;
  return { x: CENTRE + radius * Math.cos(angle), y: CENTRE + radius * Math.sin(angle) };
}

const ARC_STYLE: Record<QuestState, { stroke: string; opacity: number; width: number }> = {
  done: { stroke: 'var(--glow-gold)', opacity: 1, width: 3 },
  current: { stroke: 'var(--glow-gold)', opacity: 0.55, width: 3 },
  pending: { stroke: 'var(--border)', opacity: 1, width: 2 },
};

/**
 * The summoning ring of the analysis: rings turn while the server works, a
 * quarter lights up per finished stage, each stage gains its glyph on the
 * outer ring, a comet runs on the inner ring, and a seal appears in the
 * centre when the insight is ready. Honest: it shows the stages the server
 * reports, never a percentage. Decorative; the stage names live beside it.
 */
export function StageOrbit({
  states,
  className,
}: Readonly<{
  states: readonly QuestState[];
  className?: string;
}>) {
  const done = states.every((state) => state === 'done');
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  return (
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      aria-hidden="true"
      focusable="false"
      data-orbit={done ? 'sealed' : 'working'}
      className={cx('shrink-0 overflow-visible', className)}
    >
      <defs>
        {/* Token colours go through style: presentation attributes do not resolve var(). */}
        <radialGradient id={`orb-${id}`} cx="50%" cy="42%" r="50%">
          <stop offset="0%" style={{ stopColor: 'var(--point-gold-core)' }} />
          <stop offset="35%" style={{ stopColor: 'var(--glow-gold)' }} />
          <stop offset="70%" style={{ stopColor: 'var(--glow-emerald)', stopOpacity: 0.25 }} />
          <stop offset="100%" style={{ stopColor: 'var(--glow-emerald)', stopOpacity: 0 }} />
        </radialGradient>
      </defs>

      <g
        className={cx(
          'origin-center',
          !done && 'motion-safe:animate-[fx-rotate_64s_linear_infinite]'
        )}
        style={{ transformBox: 'fill-box' }}
      >
        <circle
          cx={CENTRE}
          cy={CENTRE}
          r={96}
          fill="none"
          style={{ stroke: 'var(--glow-gold)' }}
          strokeOpacity={0.4}
          strokeDasharray="1.5 7"
          strokeLinecap="round"
        />
      </g>
      <g
        className={cx(
          'origin-center',
          !done && 'motion-safe:animate-[fx-rotate-reverse_44s_linear_infinite]'
        )}
        style={{ transformBox: 'fill-box' }}
      >
        <circle
          cx={CENTRE}
          cy={CENTRE}
          r={58}
          fill="none"
          style={{ stroke: 'var(--glow-gold)' }}
          strokeOpacity={0.28}
          strokeWidth={0.75}
          strokeDasharray="22 12"
        />
      </g>

      {states.map((state, index) => {
        const from = onRing(index, ARC);
        const to = onRing(index + 1, ARC);
        const glyph = onRing(index + 1, GLYPH_RING);
        const style = ARC_STYLE[state];
        return (
          <g key={GLYPHS[index]} data-state={state}>
            <path
              d={`M ${from.x} ${from.y} A ${ARC} ${ARC} 0 0 0 ${to.x} ${to.y}`}
              fill="none"
              style={{ stroke: style.stroke }}
              strokeOpacity={style.opacity}
              strokeWidth={style.width}
              strokeLinecap="round"
              className={state === 'current' ? 'motion-safe:animate-pulse-soft' : undefined}
            />
            <g
              transform={`translate(${glyph.x - 11} ${glyph.y - 11})`}
              opacity={state === 'pending' ? 0.35 : 1}
              className={state === 'current' ? 'motion-safe:animate-pulse-soft' : undefined}
            >
              <circle
                cx="11"
                cy="11"
                r="11"
                style={{ fill: 'var(--bg)', stroke: style.stroke }}
                strokeWidth={1}
              />
              <path
                d={GLYPHS[index]}
                transform="translate(4 4) scale(0.583)"
                fill="none"
                style={{ stroke: state === 'pending' ? 'var(--text-muted)' : 'var(--glow-gold)' }}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
          </g>
        );
      })}

      {done ? null : (
        <g
          className="origin-center motion-safe:animate-[fx-rotate_9s_linear_infinite]"
          style={{ transformBox: 'fill-box' }}
        >
          <circle
            cx={CENTRE}
            cy={CENTRE}
            r={44}
            fill="none"
            style={{ stroke: 'var(--glow-gold)' }}
            strokeOpacity={0.9}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeDasharray={`30 ${2 * Math.PI * 44 - 30}`}
          />
        </g>
      )}

      <circle
        cx={CENTRE}
        cy={CENTRE}
        r={done ? 36 : 30}
        fill={`url(#orb-${id})`}
        className={done ? undefined : 'motion-safe:animate-pulse-soft'}
      />
      {done ? (
        <g
          data-seal="true"
          className="origin-center motion-safe:animate-[fx-pop_0.6s_cubic-bezier(0.22,1,0.36,1)_both]"
          style={{ transformBox: 'fill-box' }}
        >
          <polygon
            points={starPoints(CENTRE, CENTRE, 22, 22 * KHATAM_RATIO)}
            style={{ fill: 'var(--glow-gold)' }}
          />
          <path
            d={`M ${CENTRE - 8} ${CENTRE} l 5 5 l 11 -11`}
            fill="none"
            style={{ stroke: 'var(--on-primary)' }}
            strokeWidth={3}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      ) : null}
    </svg>
  );
}
