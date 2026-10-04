/**
 * The slow light motes behind every page, as plain data and pure steps, so the
 * drawing component stays small. Motes rise and sway on their own; nothing
 * here reads the pointer.
 */

export interface Mote {
  x: number;
  y: number;
  radius: number;
  /** Upward speed, in CSS pixels per second. */
  speed: number;
  sway: number;
  swayAmplitude: number;
  phase: number;
  twinkle: number;
  depth: number;
}

export type Random = () => number;

/** About one mote per 26 000 px², never more than 48 (a phone gets a dozen). */
export function moteCount(width: number, height: number): number {
  return Math.min(48, Math.round((width * height) / 26_000));
}

export function createMote(
  width: number,
  height: number,
  random: Random,
  fromBelow: boolean
): Mote {
  // Most motes are far (small, dim, slow), a few near: depth without a 3D engine.
  const depth = random() ** 1.6;
  return {
    x: random() * width,
    y: fromBelow ? height + 4 + random() * 24 : random() * height,
    radius: 0.8 + depth * 2.2,
    speed: 4 + depth * 12,
    sway: 0.15 + random() * 0.3,
    swayAmplitude: 2 + random() * 8,
    phase: random() * Math.PI * 2,
    twinkle: 0.3 + random() * 0.9,
    depth,
  };
}

/** One step of `dt` seconds; a mote that leaves the top comes back from below. */
export function stepMote(
  mote: Mote,
  dt: number,
  width: number,
  height: number,
  random: Random
): Mote {
  const y = mote.y - mote.speed * dt;
  if (y < -10) {
    return createMote(width, height, random, true);
  }
  return { ...mote, y };
}

/** Horizontal sway at `time` seconds, added when drawing. */
export function moteOffset(mote: Mote, time: number): number {
  return Math.sin(time * mote.sway + mote.phase) * mote.swayAmplitude;
}

/** Opacity factor at `time`: a slow twinkle between 0.4 and 1, brighter when near. */
export function moteAlpha(mote: Mote, time: number): number {
  const twinkle = 0.7 + 0.3 * Math.sin(time * mote.twinkle + mote.phase);
  return twinkle * (0.35 + mote.depth * 0.65);
}
