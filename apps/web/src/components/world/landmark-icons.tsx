import type { ReactNode, SVGProps } from 'react';

/*
 * The landmark drawings of the world picture, one per region of layout 1
 * (data/world/layout-1.json names them): line drawings on a 24-unit grid in
 * currentColor, decorative (the marker around them carries the name).
 */

type IconProps = Omit<SVGProps<SVGSVGElement>, 'children'>;

function Drawing({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

const DRAWINGS: Readonly<Record<string, ReactNode>> = {
  drop: (
    <>
      <path d="M12 3.5c3.3 4.1 5.5 7.1 5.5 10a5.5 5.5 0 0 1-11 0c0-2.9 2.2-5.9 5.5-10z" />
      <path d="M9.6 14.2a2.5 2.5 0 0 0 2.4 2.5" />
    </>
  ),
  leaf: (
    <>
      <path d="M5 19c0-8 5-14 14-14 0 9-6 14-14 14z" />
      <path d="M5 19l8-8" />
    </>
  ),
  flower: (
    <>
      <circle cx="12" cy="8" r="1.8" />
      <path d="M12 6.2c-1-2.6 2-2.6 1 0M13.7 8.6c2.7-.2 1.6 2.6-.3 1.2M10.3 8.6c-2.7-.2-1.6 2.6.3 1.2" />
      <path d="M12 9.8V20M12 15c1.6-1.8 3.4-2.2 5-2M12 17c-1.4-1.4-3-1.7-4.5-1.4" />
    </>
  ),
  book: (
    <>
      <path d="M4 5.5c2.5-1 5.5-1 8 .5 2.5-1.5 5.5-1.5 8-.5V19c-2.5-1-5.5-1-8 .5-2.5-1.5-5.5-1.5-8-.5z" />
      <path d="M12 6v13.5" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  summit: (
    <>
      <path d="M3 19l6-9 4 5 2.5-3L21 19z" />
      <circle cx="17" cy="6" r="2" />
    </>
  ),
  bridge: (
    <>
      <path d="M3 15h18" />
      <path d="M4 15c2.5-5 13.5-5 16 0" />
      <path d="M8 12.6V15M12 11.6V15M16 12.6V15" />
      <path d="M3 19c1.5-1 3-1 4.5 0s3 1 4.5 0 3-1 4.5 0 3 1 4.5 0" />
    </>
  ),
  columns: (
    <>
      <path d="M12 3.5L4 8h16z" />
      <path d="M7 9v10M12 9v10M17 9v10M4 20h16" />
    </>
  ),
  arch: (
    <>
      <path d="M5 20V10a7 7 0 0 1 14 0v10" />
      <path d="M9 20v-8a3 3 0 0 1 6 0v8" />
      <path d="M3 20h18" />
    </>
  ),
  sundial: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 12l4-5M12 3.5v2M20.5 12h-2M12 20.5v-2M3.5 12h2" />
    </>
  ),
  house: (
    <>
      <path d="M4 11l8-6.5 8 6.5" />
      <path d="M6 9.5V20h12V9.5" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  scale: (
    <>
      <path d="M12 4v16M8 20h8M5 7h14" />
      <path d="M5 7l-2.5 6a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="12" r="4" />
      <path d="M12 12h9M18 12v3M15.5 12v2" />
    </>
  ),
  path: (
    <>
      <path d="M2.5 18l6-9 3.5 5 2.5-3.5L21.5 18" />
      <path d="M9 21c1-1.5 3-2 4-3.5s.5-2.5 1.5-3.5" />
    </>
  ),
  lighthouse: (
    <>
      <path d="M10 3.5h4l1 4H9z" />
      <path d="M9.5 7.5L8 20h8L14.5 7.5" />
      <path d="M5 20h14M4 5l3 1M20 5l-3 1" />
    </>
  ),
  moon: (
    <>
      <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" />
      <path d="M17 3.5v3M15.5 5h3" />
    </>
  ),
};

/** A plain star for a drawing a later layout names and this release does not have yet. */
const UNKNOWN: ReactNode = <path d="M12 4l2.2 5.6L20 12l-5.8 2.4L12 20l-2.2-5.6L4 12l5.8-2.4z" />;

export function LandmarkIcon({ icon, ...props }: IconProps & { icon: string }) {
  return <Drawing {...props}>{DRAWINGS[icon] ?? UNKNOWN}</Drawing>;
}

export const LANDMARK_ICONS: readonly string[] = Object.keys(DRAWINGS);
