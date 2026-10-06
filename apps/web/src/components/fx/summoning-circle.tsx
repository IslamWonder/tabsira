import { cx } from '@/lib/cx';
import { KHATAM_RATIO, starPoints } from './geometry';

const RUNES = Array.from({ length: 8 }, (_, index) => {
  const angle = (index * Math.PI) / 4 - Math.PI / 2;
  return { x: 60 + 56 * Math.cos(angle), y: 60 + 56 * Math.sin(angle) };
});

/**
 * The drop zone's emblem, a summoning circle: a dotted outer ring with eight
 * points of light, a khatam turning slowly inside it, a twelve-point star
 * turning the other way, and the photo glyph at the heart. It turns faster
 * while a photo is dragged over it (motion on an event); otherwise it barely
 * moves, and not at all under reduced motion.
 */
export function SummoningCircle({
  active = false,
  size = 112,
}: Readonly<{
  active?: boolean;
  size?: number;
}>) {
  return (
    <span
      aria-hidden="true"
      data-active={active}
      className="relative inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <span
        className="absolute inset-[12%] rounded-full opacity-60"
        style={{ background: 'radial-gradient(circle, var(--glow-gold) 0%, transparent 70%)' }}
      />
      <svg
        viewBox="0 0 120 120"
        aria-hidden="true"
        focusable="false"
        className={cx(
          'absolute inset-0 h-full w-full origin-center',
          active
            ? 'motion-safe:animate-[fx-rotate_12s_linear_infinite]'
            : 'motion-safe:animate-[fx-rotate_90s_linear_infinite]'
        )}
      >
        <g fill="none" style={{ stroke: 'var(--ornament)' }}>
          <circle
            cx="60"
            cy="60"
            r="56"
            strokeWidth={0.8}
            strokeDasharray="1.5 5"
            strokeLinecap="round"
          />
          <polygon
            points={starPoints(60, 60, 50, 50 * KHATAM_RATIO)}
            strokeWidth={0.9}
            strokeOpacity={0.75}
          />
        </g>
        {RUNES.map((rune) => (
          <circle
            key={`${rune.x}-${rune.y}`}
            cx={rune.x}
            cy={rune.y}
            r={1.8}
            style={{ fill: 'var(--glow-gold)' }}
          />
        ))}
      </svg>
      <svg
        viewBox="0 0 120 120"
        aria-hidden="true"
        focusable="false"
        className={cx(
          'absolute inset-[20%] h-[60%] w-[60%] origin-center',
          active
            ? 'motion-safe:animate-[fx-rotate-reverse_9s_linear_infinite]'
            : 'motion-safe:animate-[fx-rotate-reverse_60s_linear_infinite]'
        )}
      >
        <polygon
          points={starPoints(60, 60, 56, 56 * 0.79, 12)}
          fill="none"
          style={{ stroke: 'var(--ornament)' }}
          strokeWidth={1.2}
          strokeOpacity={0.6}
        />
      </svg>
      <span className="fill-primary relative flex size-11 items-center justify-center rounded-full">
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          focusable="false"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="m17 8-5-5-5 5" />
          <path d="M12 3v12" />
        </svg>
      </span>
    </span>
  );
}
