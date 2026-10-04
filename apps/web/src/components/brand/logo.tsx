import { cx } from '@/lib/cx';
import { LOGO, MARK } from './logo-paths';

export interface LogoProps {
  /**
   * The accessible name. With it the logo is an image named so; without it,
   * it is decorative (the name is said by something next to it).
   */
  title?: string;
  className?: string;
}

function Outlines({ shape, title, className }: LogoProps & { shape: typeof MARK | typeof LOGO }) {
  const outlines = shape.paths.map((d) => <path key={d} d={d} />);
  const svg = {
    viewBox: shape.viewBox,
    fill: 'currentColor',
    focusable: 'false' as const,
    // The width follows the height the caller sets, at the drawing's own proportions.
    style: { aspectRatio: shape.viewBox.split(' ').slice(2).join(' / ') },
    className: cx('block w-auto text-brand', className),
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
export function LogoMark(props: LogoProps) {
  return <Outlines shape={MARK} {...props} />;
}

/** The mark above the Latin name «TABSIRA»: for large brand moments (the gate, the consent window). */
export function Logo(props: LogoProps) {
  return <Outlines shape={LOGO} {...props} />;
}
