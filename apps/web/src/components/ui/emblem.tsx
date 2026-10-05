import type { CSSProperties, ReactNode, SVGProps } from 'react';
import { cx } from '@/lib/cx';
import { EMBLEMS, type EmblemName } from './emblem-data';

export type { EmblemName };

type EmblemProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { name: EmblemName };

/** One emblem, drawn in the colour of its text; decorative, its label is beside it. */
export function Emblem({ name, ...props }: EmblemProps) {
  const { viewBox, paths } = EMBLEMS[name];
  return (
    <svg
      viewBox={viewBox}
      width="24"
      height="24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

const TILE = {
  sm: { box: 'size-10 rounded-[12px]', icon: 22 },
  md: { box: 'size-12 rounded-[14px]', icon: 26 },
  lg: { box: 'size-14 rounded-[16px]', icon: 30 },
} as const;

export interface EmblemTileProps {
  name: EmblemName;
  size?: keyof typeof TILE;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

/**
 * The emblem in its frame, like a skill slot of a game menu: a gold rule and a
 * second hairline inside it, a soft light from above, and the emblem engraved
 * in the landing's gold (deep gold by day, light gold by night).
 */
export function EmblemTile({ name, size = 'md', className, style, children }: EmblemTileProps) {
  const tile = TILE[size];
  return (
    <span
      aria-hidden="true"
      style={style}
      className={cx(
        'relative inline-flex shrink-0 items-center justify-center border text-[var(--landing-gold)]',
        'border-[color-mix(in_srgb,var(--landing-gold)_55%,transparent)]',
        'bg-[radial-gradient(circle_at_50%_18%,color-mix(in_srgb,var(--landing-gold)_20%,transparent),transparent_72%),linear-gradient(180deg,var(--surface),transparent)]',
        'shadow-[inset_0_0_14px_color-mix(in_srgb,var(--landing-gold)_14%,transparent),0_6px_18px_rgb(0_0_0/0.18)]',
        tile.box,
        className
      )}
    >
      <span className="pointer-events-none absolute inset-[3px] rounded-[inherit] border border-[color-mix(in_srgb,var(--landing-gold)_22%,transparent)]" />
      <Emblem name={name} width={tile.icon} height={tile.icon} />
      {children}
    </span>
  );
}
