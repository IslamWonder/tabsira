import { useId } from 'react';
import { KHATAM_RATIO, starPoints } from './geometry';

/** The three tilings of the backdrop: eight-point khatam, twelve-point star, six-point star. */
export type PatternKind = 8 | 12 | 6;

const TILE = 112;
const HALF_SIDE = 50 * Math.SQRT1_2;

function Tile({ kind }: Readonly<{ kind: PatternKind }>) {
  if (kind === 12) {
    return (
      <>
        <polygon points={starPoints(50, 50, 46, 46 * 0.79, 12)} />
        <polygon points={starPoints(50, 50, 18, 18 * 0.79, 12)} />
        <circle cx="50" cy="50" r="3" />
      </>
    );
  }
  if (kind === 6) {
    return (
      <>
        <polygon points={starPoints(50, 50, 42, 42 * 0.577, 6)} />
        <circle cx="50" cy="50" r="12" />
        <circle cx="50" cy="50" r="3" />
      </>
    );
  }
  return (
    <>
      <rect x={50 - HALF_SIDE} y={50 - HALF_SIDE} width={HALF_SIDE * 2} height={HALF_SIDE * 2} />
      <polygon points="50,0 100,50 50,100 0,50" />
      <polygon points={starPoints(50, 50, 18, 18 * KHATAM_RATIO)} />
      <circle cx="50" cy="50" r="3.2" />
    </>
  );
}

/**
 * A faint Islamic tiling behind the content (the eight-point khatam by
 * default; twelve points on the atlas, six on the world), fading toward the
 * edges. Visible in the light theme, barely there under the night aurora
 * (--pattern-opacity). Still and decorative, never in front of text.
 */
export function GeometricPattern({ kind = 8 }: Readonly<{ kind?: PatternKind }>) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-pattern={kind}
      className="absolute inset-0 h-full w-full"
      style={{ opacity: 'var(--pattern-opacity)' }}
    >
      <defs>
        <pattern
          id={`tile-${id}`}
          width={TILE}
          height={TILE}
          viewBox="0 0 100 100"
          patternUnits="userSpaceOnUse"
        >
          <g
            fill="none"
            strokeWidth={0.9}
            strokeLinejoin="round"
            style={{ stroke: 'var(--pattern-stroke)' }}
          >
            <Tile kind={kind} />
          </g>
        </pattern>
        <radialGradient id={`fade-${id}`} cx="50%" cy="40%" r="75%">
          <stop offset="0%" stopColor="#fff" stopOpacity={1} />
          <stop offset="100%" stopColor="#fff" stopOpacity={0.05} />
        </radialGradient>
        <mask id={`mask-${id}`}>
          <rect width="100%" height="100%" fill={`url(#fade-${id})`} />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill={`url(#tile-${id})`} mask={`url(#mask-${id})`} />
    </svg>
  );
}
