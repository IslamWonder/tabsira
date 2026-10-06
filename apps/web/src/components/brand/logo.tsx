import type { CSSProperties } from 'react';
import { cx } from '@/lib/cx';
import { LOGO, MARK } from './logo-paths';

export interface LogoProps {
  /**
   * The accessible name. With it the logo is an image named so; without it,
   * it is decorative (the name is said by something next to it).
   */
  title?: string;
  className?: string;
  /** Write the mark in on its first paint (fx.css «logo entrance»): the top bar's, once a page load. */
  entrance?: boolean;
  /**
   * With `entrance`: how many times the shine has been asked again since (an idle top bar).
   * Each new count replays the shine and the glow, never the writing.
   */
  shine?: number;
}

/**
 * Where each outline starts across the drawing, from 0 at its right edge to 1
 * at its left: the entrance writes the strokes in that order, the way the hand
 * writes Arabic, and the shine that follows runs the same way.
 */
export function writingOrder(shape: { viewBox: string; paths: readonly string[] }): number[] {
  const width = Number(shape.viewBox.split(' ')[2]);
  return shape.paths.map((d) => {
    const x = Number(/^M\s*(-?[\d.]+)/.exec(d)?.[1] ?? width);
    return Math.round((1 - Math.min(Math.max(x / width, 0), 1)) * 100) / 100;
  });
}

function Outlines({
  shape,
  title,
  className,
  entrance = false,
  shine = 0,
}: LogoProps & { shape: typeof MARK | typeof LOGO }) {
  const order = entrance ? writingOrder(shape) : null;
  const outlines = shape.paths.map((d, index) =>
    order === null ? (
      <path key={d} d={d} />
    ) : (
      <path
        key={d}
        d={d}
        className="fx-logo-stroke"
        style={{ '--fx-x': order[index] } as CSSProperties}
      />
    )
  );
  const svg = {
    viewBox: shape.viewBox,
    fill: 'currentColor',
    focusable: 'false' as const,
    // The width follows the height the caller sets, at the drawing's own proportions.
    style: { aspectRatio: shape.viewBox.split(' ').slice(2).join(' / ') },
    className: cx('block w-auto text-brand', entrance && 'fx-logo-glow', className),
    // Two names in turn, so that each new count starts the CSS animation again.
    'data-shine': entrance && shine > 0 ? (shine % 2 === 1 ? 'a' : 'b') : undefined,
  };
  if (title === undefined) {
    return (
      <svg aria-hidden="true" {...svg}>
        {outlines}
      </svg>
    );
  }
  return (
    <svg role="img" aria-label={title} {...svg}>
      <title>{title}</title>
      {outlines}
    </svg>
  );
}

/**
 * The designer's mark, the round calligraphic name (brand/), drawn inline
 * in `currentColor`: brand gold on night and deep gold on day through the
 * `brand` token (4.53:1 or more on every surface). Its size comes from the
 * caller's height; the width follows.
 */
export function LogoMark(props: Readonly<LogoProps>) {
  return <Outlines shape={MARK} {...props} />;
}

/** The mark above the Latin name «TABSIRA»: for large brand moments (the gate, the consent window). */
export function Logo(props: Readonly<LogoProps>) {
  return <Outlines shape={LOGO} {...props} />;
}
