/**
 * Where a point given as 0–1 ratios of the photo lands on screen.
 *
 * The server sends positions as ratios of the image it analysed (AGENTS.md,
 * lessons: convert to ratios on the server, drop what falls outside). On screen
 * the photo is full bleed with `object-fit: cover`, so part of it is cropped;
 * the ratios are mapped through the same crop, and a point that the crop hides
 * is reported as not visible instead of being drawn at a wrong place.
 */

export interface Size {
  readonly width: number;
  readonly height: number;
}

export interface Ratios {
  readonly x: number;
  readonly y: number;
}

/** Percentages of the box, and whether the point is inside the visible crop. */
export interface Placement {
  readonly left: number;
  readonly top: number;
  readonly visible: boolean;
}

export type HorizontalSide = 'toRight' | 'center' | 'toLeft';
export type VerticalSide = 'above' | 'below';

export function isRatio(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

/** Before the box is measured (server render, first paint) the ratios are used as they are. */
export function coverPlacement(point: Ratios, image: Size, box: Size | null): Placement {
  if (box === null || box.width <= 0 || box.height <= 0 || image.width <= 0 || image.height <= 0) {
    return { left: point.x * 100, top: point.y * 100, visible: true };
  }
  const scale = Math.max(box.width / image.width, box.height / image.height);
  const shownWidth = image.width * scale;
  const shownHeight = image.height * scale;
  const x = (box.width - shownWidth) / 2 + point.x * shownWidth;
  const y = (box.height - shownHeight) / 2 + point.y * shownHeight;
  return {
    left: (x / box.width) * 100,
    top: (y / box.height) * 100,
    visible: x >= 0 && x <= box.width && y >= 0 && y <= box.height,
  };
}

/**
 * Where the label goes so it stays in the frame and clear of its neighbour
 * (Law of Proximity keeps it next to its point): above the orb in the lower
 * half of the photo, below it in the upper half; centred, unless the orb is
 * near a side, where the label grows toward the middle.
 */
export function labelSides(placement: Placement): {
  horizontal: HorizontalSide;
  vertical: VerticalSide;
} {
  const farSide = placement.left > 78 ? 'toLeft' : 'center';
  const horizontal = placement.left < 22 ? 'toRight' : farSide;
  return { horizontal, vertical: placement.top > 50 ? 'above' : 'below' };
}

/** Row and column (0–2) of a point in a 3 × 3 grid of the photo, for its spoken position. */
export function gridCell(point: Ratios): { row: 0 | 1 | 2; column: 0 | 1 | 2 } {
  const cell = (value: number) => Math.min(2, Math.floor(value * 3)) as 0 | 1 | 2;
  return { row: cell(point.y), column: cell(point.x) };
}

/** A rectangle in percent of its box. */
export interface Frame {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

/**
 * Where an `object-fit: contain` photo sits inside its box, in percent of the
 * box: the whole photo, uncropped, so a box given as ratios of the photo can be
 * laid over it exactly (choosing a focus needs every thing in view). Before the
 * box is measured the frame is the whole box.
 */
export function containFrame(image: Size, box: Size | null): Frame {
  if (box === null || box.width <= 0 || box.height <= 0 || image.width <= 0 || image.height <= 0) {
    return { left: 0, top: 0, width: 100, height: 100 };
  }
  const scale = Math.min(box.width / image.width, box.height / image.height);
  const width = (image.width * scale) / box.width;
  const height = (image.height * scale) / box.height;
  return {
    left: ((1 - width) / 2) * 100,
    top: ((1 - height) / 2) * 100,
    width: width * 100,
    height: height * 100,
  };
}
