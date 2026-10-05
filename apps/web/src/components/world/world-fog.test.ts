import { describe, expect, it, vi } from 'vitest';
import { circleAt, drawFog, easeOut, REVEAL_DURATION_MS } from './world-fog';

function context() {
  const gradient = { addColorStop: vi.fn() };
  const operations: string[] = [];
  const fake = {
    operations,
    gradient,
    set globalCompositeOperation(value: string) {
      operations.push(value);
    },
    get globalCompositeOperation() {
      return operations.at(-1) ?? 'source-over';
    },
    fillStyle: '' as unknown,
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    createRadialGradient: vi.fn(() => gradient),
    createLinearGradient: vi.fn(() => gradient),
  };
  return fake;
}

const SIZE = { width: 1000, height: 600 };

describe('the clouds', () => {
  it('eases out, from nothing to whole', () => {
    expect(easeOut(-1)).toBe(0);
    expect(easeOut(0.5)).toBeCloseTo(0.875);
    expect(easeOut(2)).toBe(1);
  });

  it('cover everything first, then cut each reveal with a feathered edge', () => {
    const fake = context();
    const clouds = {} as CanvasImageSource;

    drawFog(fake as unknown as CanvasRenderingContext2D, SIZE, clouds, [
      { x: 0.5, y: 0.5, radius: 0.1, amount: 1 },
      { x: 0.2, y: 0.2, radius: 0.1, amount: 0 },
    ]);

    expect(fake.drawImage).toHaveBeenCalledWith(clouds, 0, 0, 1000, 600);
    expect(fake.operations).toEqual(['source-over', 'destination-out', 'source-over']);
    // A circle that has not started cuts nothing.
    expect(fake.arc).toHaveBeenCalledOnce();
    expect(fake.arc).toHaveBeenCalledWith(500, 300, 100, 0, Math.PI * 2);
    expect(fake.createRadialGradient).toHaveBeenCalledWith(500, 300, 0, 500, 300, 100);
    const stops = fake.gradient.addColorStop.mock.calls;
    expect(stops.at(0)).toEqual([0, 'rgba(0, 0, 0, 1)']);
    expect(stops.at(-1)).toEqual([1, 'rgba(0, 0, 0, 0)']);
  });

  it('stay opaque when their picture could not load: the ground never shows through', () => {
    const fake = context();

    drawFog(fake as unknown as CanvasRenderingContext2D, SIZE, null, []);

    expect(fake.drawImage).not.toHaveBeenCalled();
    expect(fake.fillRect).toHaveBeenCalledWith(0, 0, 1000, 600);
  });

  it('part as a widening circle, and along the way for patience', () => {
    const circle = { x: 0.5, y: 0.5, radius: 0.1 };
    expect(circleAt(circle, 'water', 0)).toEqual({ ...circle, amount: 0 });
    expect(circleAt(circle, 'water', REVEAL_DURATION_MS)).toEqual({ ...circle, amount: 1 });

    const early = circleAt(circle, 'patience', REVEAL_DURATION_MS / 4);
    expect(early.x).toBeLessThan(0.5);
    expect(early.y).toBeGreaterThan(0.5);
    expect(circleAt(circle, 'patience', REVEAL_DURATION_MS)).toEqual({ ...circle, amount: 1 });
  });
});
