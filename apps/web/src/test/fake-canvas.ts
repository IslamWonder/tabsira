import { vi } from 'vitest';

/** A 2D context that records calls, for the canvas effects. */
export function fakeContext() {
  return {
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    globalAlpha: 1,
    fillStyle: '',
    shadowColor: '',
    shadowBlur: 0,
  };
}

/** requestAnimationFrame under the test's control: `step(ms)` runs the pending frame. */
export function manualFrames() {
  let pending: FrameRequestCallback | null = null;
  let now = 0;
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((callback: FrameRequestCallback) => {
      pending = callback;
      return 1;
    })
  );
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn(() => {
      pending = null;
    })
  );
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  return {
    step(ms: number) {
      now += ms;
      const callback = pending;
      pending = null;
      callback?.(now);
    },
    get pending() {
      return pending !== null;
    },
  };
}
