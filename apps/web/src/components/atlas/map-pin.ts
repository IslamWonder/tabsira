/**
 * The atlas pin (the owners' choice of 5 October 2026, «A»): an emerald drop in
 * a gold rim with the eight-point khatam inside, drawn for TABSIRA, no
 * third-party asset. It is painted here on a canvas, synchronously, at twice
 * its size so it stays sharp, and handed to the map as an image; where no
 * canvas can draw (an old browser, a test), there is no pin and the map keeps
 * its circles.
 */

export const PIN_IMAGE = 'tabsira-pin';
/** The pin is drawn on a 48 × 60 grid; its tip, the place, is at the bottom centre. */
export const PIN_WIDTH = 48;
export const PIN_HEIGHT = 60;
export const PIN_PIXEL_RATIO = 2;

const RIM = 'M24 56C24 56 6 36 6 21A18 18 0 0 1 42 21C42 36 24 56 24 56Z';
const DROP = 'M24 52.5C24 52.5 8.6 35 8.6 21.2A15.4 15.4 0 0 1 39.4 21.2C39.4 35 24 52.5 24 52.5Z';
// The khatam: two squares of side 11 around (24, 20), one turned by 45 degrees.
const SQUARE = 'M18.5 14.5h11v11h-11z';
const DIAMOND = 'M24 12.22L31.78 20L24 27.78L16.22 20z';

const GOLD: readonly [number, string][] = [
  [0, '#F3DFA8'],
  [0.5, '#DFBD77'],
  [1, '#A8812F'],
];
const EMERALD: readonly [number, string][] = [
  [0, '#1F7A5C'],
  [1, '#0A3A2C'],
];

function gradient(fill: CanvasGradient, stops: readonly [number, string][]): CanvasGradient {
  for (const [at, colour] of stops) {
    fill.addColorStop(at, colour);
  }
  return fill;
}

/** The pin's pixels, ready for `map.addImage`; null where a canvas cannot draw. */
export function drawPin(): ImageData | null {
  if (typeof document === 'undefined' || typeof Path2D === 'undefined') {
    return null;
  }
  const canvas = document.createElement('canvas');
  canvas.width = PIN_WIDTH * PIN_PIXEL_RATIO;
  canvas.height = PIN_HEIGHT * PIN_PIXEL_RATIO;
  const context = canvas.getContext('2d');
  if (context === null) {
    return null;
  }
  context.scale(PIN_PIXEL_RATIO, PIN_PIXEL_RATIO);
  const gold = gradient(context.createLinearGradient(0, 3, 0, 56), GOLD);

  // Its shadow on the ground, under the tip.
  context.fillStyle = 'rgba(0, 0, 0, 0.28)';
  context.beginPath();
  context.ellipse(24, 56, 7, 2.2, 0, 0, Math.PI * 2);
  context.fill();

  // The gold rim, lifted from the map by a soft shadow, then the emerald drop inside it.
  context.save();
  context.shadowColor = 'rgba(0, 0, 0, 0.45)';
  context.shadowBlur = 3.2;
  context.shadowOffsetY = 2;
  context.fillStyle = gold;
  context.fill(new Path2D(RIM));
  context.restore();
  context.fillStyle = gradient(context.createRadialGradient(24, 18, 0, 24, 22, 26), EMERALD);
  context.fill(new Path2D(DROP));

  // The khatam in gold, and its bright heart.
  context.strokeStyle = gold;
  context.lineWidth = 1.4;
  context.lineJoin = 'round';
  context.stroke(new Path2D(SQUARE));
  context.stroke(new Path2D(DIAMOND));
  context.fillStyle = gold;
  context.beginPath();
  context.arc(24, 20, 3.2, 0, Math.PI * 2);
  context.fill();

  return context.getImageData(0, 0, canvas.width, canvas.height);
}
