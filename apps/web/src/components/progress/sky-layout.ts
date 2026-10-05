/**
 * Where each star of the sky of meanings is drawn, in pixels of its field.
 *
 * The server gives every meaning a fixed place from its name alone (a ratio of
 * the field), so the same meaning always comes back to the same spot. Two
 * names may still land on each other, on the heading or on the dock, so the
 * stars are laid out oldest first: a star keeps its own place when it is free,
 * and otherwise takes the nearest free place along one fixed spiral. A newer
 * meaning therefore never moves an older one, and nothing here is random.
 * A star with no free place left is not drawn; the sky's list still holds it.
 */

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StarSize {
  key: string;
  /** The server's place, ratios of the field measured from its left and top edges. */
  x: number;
  y: number;
  /** The star button and its name under it, as measured once the font is in. */
  width: number;
  height: number;
}

export interface Placement {
  /** The centre of the star's light, in pixels of the field. */
  placed: Map<string, { x: number; y: number }>;
  /** Stars with no free place in this field; never hidden from the sky's list. */
  unplaced: string[];
}

/** The light sits at the top of its box, centred; its name hangs below it. */
export const LIGHT_OFFSET = 22;
const GAP = 6;
const STEP = 14;
const RINGS = 40;

function overlaps(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width + GAP &&
    b.x < a.x + a.width + GAP &&
    a.y < b.y + b.height + GAP &&
    b.y < a.y + a.height + GAP
  );
}

function inside(box: Box, field: { width: number; height: number }): boolean {
  return (
    box.x >= 0 &&
    box.y >= 0 &&
    box.x + box.width <= field.width &&
    box.y + box.height <= field.height
  );
}

function boxAt(star: StarSize, x: number, y: number): Box {
  return { x: x - star.width / 2, y: y - LIGHT_OFFSET, width: star.width, height: star.height };
}

/** The candidate centres around a place, nearest first: the place, then rings of eight more points each. */
export function* spiral(x: number, y: number): Generator<[number, number]> {
  yield [x, y];
  for (let ring = 1; ring <= RINGS; ring += 1) {
    const radius = ring * STEP;
    const points = 8 * ring;
    for (let index = 0; index < points; index += 1) {
      const angle = (index / points) * 2 * Math.PI;
      yield [x + radius * Math.cos(angle), y + radius * Math.sin(angle)];
    }
  }
}

/**
 * Lay the stars out in the order given (the order their meanings were first
 * learned), keeping clear of each other and of the reserved boxes.
 */
export function placeStars(
  stars: readonly StarSize[],
  field: { width: number; height: number },
  reserved: readonly Box[]
): Placement {
  const taken: Box[] = [...reserved];
  const placed = new Map<string, { x: number; y: number }>();
  const unplaced: string[] = [];
  for (const star of stars) {
    let found: [number, number] | null = null;
    for (const [x, y] of spiral(star.x * field.width, star.y * field.height)) {
      const box = boxAt(star, x, y);
      if (inside(box, field) && !taken.some((other) => overlaps(box, other))) {
        found = [x, y];
        taken.push(box);
        break;
      }
    }
    if (found === null) {
      unplaced.push(star.key);
    } else {
      placed.set(star.key, { x: found[0], y: found[1] });
    }
  }
  return { placed, unplaced };
}
