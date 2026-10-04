import { describe, expect, it, vi } from 'vitest';
import { BURST_EVENT, burstFrom, particleAlpha, spawnBurst, stepParticles } from './burst';
import { createMote, moteAlpha, moteCount, moteOffset, stepMote } from './motes';

const half = () => 0.5;

describe('motes', () => {
  it('scale with the area, never past 48', () => {
    expect(moteCount(375, 812)).toBe(12);
    expect(moteCount(4000, 4000)).toBe(48);
  });

  it('start anywhere, or just below the frame when they come back', () => {
    const inside = createMote(100, 200, half, false);
    expect(inside.y).toBe(100);
    expect(createMote(100, 200, half, true).y).toBe(216);
    expect(inside.radius).toBeGreaterThan(0.8);
  });

  it('rise, and come back from below once past the top', () => {
    const mote = createMote(100, 200, half, false);
    const risen = stepMote(mote, 1, 100, 200, half);
    expect(risen.y).toBeLessThan(mote.y);
    const gone = stepMote({ ...mote, y: -9 }, 1, 100, 200, half);
    expect(gone.y).toBeGreaterThan(200);
  });

  it('sway and twinkle within bounds', () => {
    const mote = createMote(100, 200, half, false);
    expect(Math.abs(moteOffset(mote, 3))).toBeLessThanOrEqual(mote.swayAmplitude);
    const alpha = moteAlpha(mote, 3);
    expect(alpha).toBeGreaterThan(0);
    expect(alpha).toBeLessThanOrEqual(1);
  });
});

describe('burst', () => {
  it('spawns a ring of particles at the point', () => {
    const particles = spawnBurst({ x: 10, y: 20 }, half);
    expect(particles).toHaveLength(36);
    expect(particles[0]).toMatchObject({ x: 10, y: 20, life: 0, star: false, tone: 1 });
  });

  it('moves particles and drops the spent ones', () => {
    const [particle] = spawnBurst({ x: 0, y: 0 }, half);
    const moved = stepParticles([particle as NonNullable<typeof particle>], 0.1);
    expect(moved[0]?.x).not.toBe(0);
    expect(stepParticles(moved, 5)).toEqual([]);
  });

  it('fades out over the last third of a life', () => {
    const [particle] = spawnBurst({ x: 0, y: 0 }, half);
    const p = particle as NonNullable<typeof particle>;
    expect(particleAlpha(p)).toBe(1);
    expect(particleAlpha({ ...p, life: p.max * 0.83 })).toBeCloseTo(0.5, 1);
  });

  it('is raised from the centre of an element', () => {
    const listener = vi.fn();
    window.addEventListener(BURST_EVENT, listener);
    const element = document.createElement('div');
    vi.spyOn(element, 'getBoundingClientRect').mockReturnValue(new DOMRect(10, 20, 100, 40));
    burstFrom(element);
    const event = listener.mock.lastCall?.[0] as CustomEvent | undefined;
    expect(event?.detail).toEqual({ x: 60, y: 40 });
    window.removeEventListener(BURST_EVENT, listener);
  });
});
