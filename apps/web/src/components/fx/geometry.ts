/** Points of a star polygon: `points` tips alternating between the outer and inner radius. */
export function starPoints(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
  points = 8,
  rotation = -Math.PI / 2
): string {
  return Array.from({ length: points * 2 }, (_, i) => {
    const radius = i % 2 === 0 ? outer : inner;
    const angle = rotation + (i * Math.PI) / points;
    return `${(cx + radius * Math.cos(angle)).toFixed(2)},${(cy + radius * Math.sin(angle)).toFixed(2)}`;
  }).join(' ');
}

/** Inner to outer radius of the eight-point khatam made of two squares. */
export const KHATAM_RATIO = 0.7654;
