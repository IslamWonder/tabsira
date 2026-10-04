/**
 * A one-shot burst of light for the end of the journey (the done button, Peak-End
 * rule), as an event any component can raise and pure particle steps the
 * single <BurstLayer /> draws.
 */

export const BURST_EVENT = 'tabsira:burst';

export interface BurstRequest {
  /** Viewport pixels. */
  x: number;
  y: number;
}

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  size: number;
  rotation: number;
  spin: number;
  /** An eight-point star, or a round spark. */
  star: boolean;
  /** Index into the palette: gold, emerald, ivory. */
  tone: 0 | 1 | 2;
}

export type Random = () => number;

/** Bursts from the centre of an element (the button just pressed). */
export function burstFrom(element: Element): void {
  const box = element.getBoundingClientRect();
  window.dispatchEvent(
    new CustomEvent<BurstRequest>(BURST_EVENT, {
      detail: { x: box.left + box.width / 2, y: box.top + box.height / 2 },
    })
  );
}

const COUNT = 36;

export function spawnBurst({ x, y }: BurstRequest, random: Random): Particle[] {
  return Array.from({ length: COUNT }, () => {
    const angle = random() * Math.PI * 2;
    const speed = 120 + random() * 340;
    return {
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 80,
      life: 0,
      max: 0.6 + random() * 0.7,
      size: 1.5 + random() * 3,
      rotation: random() * Math.PI * 2,
      spin: (random() - 0.5) * 12,
      star: random() < 0.35,
      tone: Math.min(2, Math.floor(random() * 3)) as 0 | 1 | 2,
    };
  });
}

/** One step of `dt` seconds: drag, a little gravity, and the dead ones removed. */
export function stepParticles(particles: readonly Particle[], dt: number): Particle[] {
  const drag = Math.max(0, 1 - 3 * dt);
  return particles
    .map((p) => ({
      ...p,
      life: p.life + dt,
      vx: p.vx * drag,
      vy: p.vy * drag + 260 * dt,
      x: p.x + p.vx * dt,
      y: p.y + p.vy * dt,
      rotation: p.rotation + p.spin * dt,
    }))
    .filter((p) => p.life < p.max);
}

/** Fades out over the last third of its life. */
export function particleAlpha(particle: Particle): number {
  const t = particle.life / particle.max;
  return t < 0.66 ? 1 : 1 - (t - 0.66) / 0.34;
}
