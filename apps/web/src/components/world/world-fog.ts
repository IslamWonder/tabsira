import type { WorldTheme } from '@/world/api';
import type { Size } from './world-geometry';

/*
 * The clouds over the world picture (decision 59): the cloud texture drawn
 * whole and opaque, then each reveal cut out of it with `destination-out`, a
 * clear middle and a feathered edge, so circles join (a union) and an edge
 * melts into the clouds instead of ending in a hard ring. The mask is drawing
 * only: nothing still under the clouds is sent to the page in the first place.
 */

/** A circle to cut, in ratios of the picture, and how far its reveal has come (0 to 1). */
export interface FogCircle {
  x: number;
  y: number;
  radius: number;
  amount: number;
}

/** A reveal's effect lasts this long, eased out; the landmark appears once the clouds start to part. */
export const REVEAL_DURATION_MS = 1400;
export const LANDMARK_DELAY_MS = 420;
/** Several new reveals start a little apart, one after the other. */
export const REVEAL_STAGGER_MS = 260;

export function easeOut(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return 1 - (1 - clamped) ** 3;
}

/**
 * The circle of a reveal `elapsed` milliseconds into its effect. It widens from
 * nothing; patience opens along its path instead, its middle travelling to the
 * landmark as it widens, so the way is uncovered step by step.
 */
export function circleAt(
  circle: Omit<FogCircle, 'amount'>,
  theme: WorldTheme,
  elapsed: number
): FogCircle {
  const amount = easeOut(elapsed / REVEAL_DURATION_MS);
  if (theme !== 'patience') {
    return { ...circle, amount };
  }
  const behind = 1 - amount;
  return {
    x: circle.x - circle.radius * 0.6 * behind,
    y: circle.y + circle.radius * 0.6 * behind,
    radius: circle.radius,
    amount,
  };
}

// Where the edge starts to soften, and how much cloud is left at three quarters of the way.
const CLEAR_TO = 0.6;
const HALF_AT = 0.82;

/** Cut one circle out of what is drawn: clear in the middle, fading into the clouds at its edge. */
function cut(context: CanvasRenderingContext2D, size: Size, circle: FogCircle): void {
  const radius = circle.radius * size.width * circle.amount;
  if (radius <= 0) {
    return;
  }
  const x = circle.x * size.width;
  const y = circle.y * size.height;
  const edge = context.createRadialGradient(x, y, 0, x, y, radius);
  edge.addColorStop(0, 'rgba(0, 0, 0, 1)');
  edge.addColorStop(CLEAR_TO, 'rgba(0, 0, 0, 1)');
  edge.addColorStop(HALF_AT, 'rgba(0, 0, 0, 0.55)');
  edge.addColorStop(1, 'rgba(0, 0, 0, 0)');
  context.fillStyle = edge;
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();
}

/** Opaque clouds of the brand's greens, for a cloud picture that did not load: the ground never shows through. */
function fallbackClouds(context: CanvasRenderingContext2D, size: Size): void {
  const sky = context.createLinearGradient(0, 0, size.width, size.height);
  sky.addColorStop(0, '#dcebe4');
  sky.addColorStop(0.5, '#b9d6cb');
  sky.addColorStop(1, '#8fbcae');
  context.fillStyle = sky;
  context.fillRect(0, 0, size.width, size.height);
}

/** Draw the whole cloud layer for these circles. `clouds` is null when its picture could not load. */
export function drawFog(
  context: CanvasRenderingContext2D,
  size: Size,
  clouds: CanvasImageSource | null,
  circles: readonly FogCircle[]
): void {
  context.globalCompositeOperation = 'source-over';
  context.clearRect(0, 0, size.width, size.height);
  if (clouds === null) {
    fallbackClouds(context, size);
  } else {
    context.drawImage(clouds, 0, 0, size.width, size.height);
  }
  context.globalCompositeOperation = 'destination-out';
  for (const circle of circles) {
    cut(context, size, circle);
  }
  context.globalCompositeOperation = 'source-over';
}
