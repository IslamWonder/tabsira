import { describe, expect, it } from 'vitest';
import {
  canvasSize,
  centerOf,
  centerOn,
  clampCamera,
  MAX_CANVAS_SIDE,
  MAX_ZOOM,
  MIN_ZOOM,
  panBy,
  stageSize,
  zoomAround,
  zoomStep,
} from './world-geometry';

const PHONE = { width: 390, height: 700 };
const DESKTOP = { width: 1440, height: 828 };

describe('the world geometry', () => {
  it('covers the viewport at zoom 1 with the picture in its own 3:2 frame', () => {
    // A tall phone sees a window of the large world, never a shrunken picture.
    expect(stageSize(PHONE)).toEqual({ width: 1050, height: 700 });
    expect(stageSize(DESKTOP)).toEqual({ width: 1440, height: 960 });
  });

  it('never lets the picture leave a gap at any edge, at any zoom', () => {
    expect(clampCamera({ x: 50, y: 50, zoom: 1 }, PHONE)).toEqual({ x: 0, y: 0, zoom: 1 });
    expect(clampCamera({ x: -5000, y: -5000, zoom: 1 }, PHONE)).toEqual({
      x: 390 - 1050,
      y: 0,
      zoom: 1,
    });
    expect(clampCamera({ x: 0, y: 0, zoom: 9 }, PHONE).zoom).toBe(MAX_ZOOM);
    expect(clampCamera({ x: 0, y: 0, zoom: 0.2 }, PHONE).zoom).toBe(MIN_ZOOM);
  });

  it('centres a point of the picture as far as the edges allow, and reads the centre back', () => {
    const camera = centerOn(PHONE, { x: 0.5, y: 0.5 }, 1);
    expect(camera).toEqual({ x: 195 - 525, y: 0, zoom: 1 });
    expect(centerOf(camera, PHONE)).toEqual({ x: 0.5, y: 0.5 });
    // A corner cannot come to the middle: the picture stops at its edge.
    expect(centerOn(PHONE, { x: 0, y: 0 }, 1)).toEqual({ x: 0, y: 0, zoom: 1 });
  });

  it('pans and zooms about a point that stays under the pointer', () => {
    const start = centerOn(DESKTOP, { x: 0.5, y: 0.5 }, 1);
    // At zoom 1 a desktop already sees the picture's whole width: it moves up and down only.
    expect(panBy(start, DESKTOP, -40, -30)).toEqual({ ...start, y: start.y - 30 });
    const near = centerOn(DESKTOP, { x: 0.5, y: 0.5 }, 2);
    expect(panBy(near, DESKTOP, -40, -30)).toEqual({ zoom: 2, x: near.x - 40, y: near.y - 30 });

    const anchor = { x: 700, y: 400 };
    const zoomed = zoomAround(start, DESKTOP, 2, anchor);
    const before = (anchor.x - start.x) / start.zoom;
    expect((anchor.x - zoomed.x) / zoomed.zoom).toBeCloseTo(before);
    expect(zoomStep(start, DESKTOP, 1).zoom).toBe(1.25);
    expect(zoomStep(start, DESKTOP, -1).zoom).toBe(MIN_ZOOM);
  });

  it('caps the canvas so a dense phone never holds a huge texture', () => {
    expect(canvasSize({ width: 1050, height: 700 }, 3)).toEqual({ width: 2048, height: 1365 });
    expect(canvasSize({ width: 800, height: 533 }, 2)).toEqual({ width: 1600, height: 1066 });
    expect(canvasSize({ width: 800, height: 533 }, 0)).toEqual({ width: 800, height: 533 });
    expect(Math.max(...Object.values(canvasSize({ width: 3000, height: 2000 }, 2)))).toBe(
      MAX_CANVAS_SIDE
    );
  });
});
