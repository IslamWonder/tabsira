import type { CSSProperties } from 'react';
import { KHATAM_RATIO, starPoints } from '@/components/fx/geometry';
import { LightMotes } from '@/components/fx/light-motes';
import { cx } from '@/lib/cx';

/**
 * A large eight-point khatam drawn in thin gold lines, turning very slowly:
 * an ornament behind a scene, never in front of text.
 */
export function KhatamStar({ className, style }: { className?: string; style?: CSSProperties }) {
  const half = 50 * Math.SQRT1_2;
  return (
    <svg
      viewBox="0 0 100 100"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="0.35"
      className={cx('pointer-events-none', className)}
      style={style}
    >
      <rect x={50 - half} y={50 - half} width={half * 2} height={half * 2} />
      <rect
        x={50 - half}
        y={50 - half}
        width={half * 2}
        height={half * 2}
        transform="rotate(45 50 50)"
      />
      <polygon points={starPoints(50, 50, 30, 30 * KHATAM_RATIO)} />
      <circle cx="50" cy="50" r="46" strokeDasharray="0.6 2.4" />
      <circle cx="50" cy="50" r="12" />
    </svg>
  );
}

/**
 * The hero's living sky, behind its words and its phone: two glows that drift,
 * a khatam turning behind the phone, and gold dust rising (the same motes as
 * the page's backdrop, which stop with the motion setting). Decoration only.
 */
export function HeroAtmosphere() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <span className="absolute -top-1/3 -right-1/4 size-[70%] animate-[fx-drift-a_26s_ease-in-out_infinite] rounded-full bg-[radial-gradient(closest-side,rgb(223_189_119/0.22),transparent_72%)]" />
      <span className="absolute -bottom-1/3 -left-1/4 size-[80%] animate-[fx-drift-b_32s_ease-in-out_infinite] rounded-full bg-[radial-gradient(closest-side,rgb(63_214_154/0.2),transparent_72%)]" />
      <div className="fx-ring-in absolute top-1/2 left-1/2 size-[560px] -translate-x-1/2 -translate-y-1/2 tablet:left-1/4 tablet:size-[640px]">
        <KhatamStar className="fx-turn-slow size-full text-[rgb(223_189_119/0.16)]" />
      </div>
      <LightMotes />
    </div>
  );
}
