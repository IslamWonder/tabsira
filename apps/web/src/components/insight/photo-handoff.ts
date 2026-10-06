import type { Route } from 'next';

/** The name the scan's photo and the insight's photo share, so one turns into the other. */
export const PHOTO_MORPH = 'insight-photo';

export interface HandedPhoto {
  src: string;
  width: number;
  height: number;
  /** Where the round way back on the photo leads: the scan it came from. */
  backHref: Route;
}

/*
 * The insight reads itself in the browser after the page changed, so its photo
 * comes a moment too late to be the end of a morph. The scan, which already
 * shows the photo, hands it over as it opens one of its insights; the insight
 * shows it at once, in the same commit as the navigation, until its own photo
 * is read. Kept in memory for one insight only, and only ever set in the
 * browser, by the reader's own tap.
 */
let handed: { insightId: string; photo: HandedPhoto } | null = null;

export function handPhoto(insightId: string, photo: HandedPhoto): void {
  handed = { insightId, photo };
}

export function handedPhoto(insightId: string): HandedPhoto | null {
  return handed?.insightId === insightId ? handed.photo : null;
}

/** For tests. */
export function forgetHandedPhoto(): void {
  handed = null;
}
