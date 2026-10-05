/*
 * One geometry for the ground, the clouds and the landmarks (decision 59). The
 * picture keeps its own 3:2 frame; at zoom 1 it covers the viewport (as wide
 * as the viewport and as tall, whichever needs more), so a narrow phone sees a
 * window of the large world and moves it, never a shrunken picture. Points of
 * the picture are ratios: x of its width from its left edge, y of its height
 * from its top, whatever the direction of the text. The camera is the
 * translation of the picture's top-left corner in the viewport, and its zoom.
 */

/** The world picture is 1536 by 1024. */
export const PICTURE_RATIO = 1.5;
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 2;
/** One press of a zoom button or key. */
export const ZOOM_STEP = 0.25;
/** One press of an arrow key moves the view this many pixels. */
export const PAN_STEP = 64;
/** The fog canvas never exceeds this many pixels a side, whatever the screen's density. */
export const MAX_CANVAS_SIDE = 2048;

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Camera {
  x: number;
  y: number;
  zoom: number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/** The picture's size at zoom 1 for a viewport: no gap on any side. */
export function stageSize(view: Size): Size {
  const width = Math.max(view.width, view.height * PICTURE_RATIO);
  return { width, height: width / PICTURE_RATIO };
}

export function clampZoom(zoom: number): number {
  return clamp(zoom, MIN_ZOOM, MAX_ZOOM);
}

/** Keep the picture over the whole viewport: moving it never shows what lies beyond its edges. */
export function clampCamera(camera: Camera, view: Size): Camera {
  const stage = stageSize(view);
  const zoom = clampZoom(camera.zoom);
  return {
    zoom,
    x: clamp(camera.x, view.width - stage.width * zoom, 0),
    y: clamp(camera.y, view.height - stage.height * zoom, 0),
  };
}

/** The camera that puts a point of the picture at the middle of the viewport, as near as the edges allow. */
export function centerOn(view: Size, target: Point, zoom: number): Camera {
  const stage = stageSize(view);
  const scale = clampZoom(zoom);
  return clampCamera(
    {
      zoom: scale,
      x: view.width / 2 - target.x * stage.width * scale,
      y: view.height / 2 - target.y * stage.height * scale,
    },
    view
  );
}

/** The point of the picture at the middle of the viewport, to keep in place when the viewport changes. */
export function centerOf(camera: Camera, view: Size): Point {
  const stage = stageSize(view);
  return {
    x: (view.width / 2 - camera.x) / (stage.width * camera.zoom),
    y: (view.height / 2 - camera.y) / (stage.height * camera.zoom),
  };
}

export function panBy(camera: Camera, view: Size, dx: number, dy: number): Camera {
  return clampCamera({ ...camera, x: camera.x + dx, y: camera.y + dy }, view);
}

/** Zoom while the point under `anchor` (viewport pixels) stays under it. */
export function zoomAround(camera: Camera, view: Size, zoom: number, anchor: Point): Camera {
  const scale = clampZoom(zoom);
  const pictureX = (anchor.x - camera.x) / camera.zoom;
  const pictureY = (anchor.y - camera.y) / camera.zoom;
  return clampCamera(
    { zoom: scale, x: anchor.x - pictureX * scale, y: anchor.y - pictureY * scale },
    view
  );
}

/** Zoom by one step about the middle of the viewport. */
export function zoomStep(camera: Camera, view: Size, direction: 1 | -1): Camera {
  return zoomAround(camera, view, camera.zoom + direction * ZOOM_STEP, {
    x: view.width / 2,
    y: view.height / 2,
  });
}

/** The canvas's own pixels for a stage: the screen's density, capped so a phone never holds a huge texture. */
export function canvasSize(stage: Size, density: number): Size {
  const scale = Math.min(Math.max(density, 1), 2, MAX_CANVAS_SIDE / stage.width);
  return { width: Math.round(stage.width * scale), height: Math.round(stage.height * scale) };
}
