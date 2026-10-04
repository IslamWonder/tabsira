import { KHATAM_RATIO, starPoints } from './geometry';

const CORNERS = ['top-start', 'top-end', 'bottom-start', 'bottom-end'] as const;

/**
 * The four corners of an RPG panel: a framed corner, an inner echo, two leaf
 * tendrils and a small khatam at the knot, in the ornament token. The lines
 * draw themselves in once when the panel appears (motion on display only).
 */
export function OrnateCorners() {
  return (
    <>
      {CORNERS.map((corner) => (
        <svg
          key={corner}
          viewBox="0 0 40 40"
          fill="none"
          aria-hidden="true"
          focusable="false"
          className={`fx-corner fx-corner--${corner}`}
        >
          <path
            className="fx-draw"
            pathLength={1}
            d="M0.75 40V12.5C0.75 6 6 0.75 12.5 0.75H40"
            stroke="currentColor"
            strokeWidth={1}
            strokeOpacity={0.9}
          />
          <path
            className="fx-draw"
            pathLength={1}
            d="M8 31V17.5C8 12.3 12.3 8 17.5 8H31"
            stroke="currentColor"
            strokeWidth={0.8}
            strokeOpacity={0.45}
          />
          <path
            className="fx-draw"
            pathLength={1}
            d="M17.5 8C21 8 22.5 5.5 24.5 3.5M8 17.5C8 21 5.5 22.5 3.5 24.5"
            stroke="currentColor"
            strokeWidth={0.8}
            strokeOpacity={0.6}
            strokeLinecap="round"
          />
          <polygon
            points={starPoints(8, 8, 3.6, 3.6 * KHATAM_RATIO)}
            fill="currentColor"
            fillOpacity={0.9}
          />
        </svg>
      ))}
    </>
  );
}
