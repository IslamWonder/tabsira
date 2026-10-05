import { afterEach, describe, expect, it, vi } from 'vitest';
import { drawPin, PIN_HEIGHT, PIN_PIXEL_RATIO, PIN_WIDTH } from './map-pin';

/** A 2D context that records what the pin draws. */
function pinContext() {
  const gradient = () => ({ addColorStop: vi.fn() });
  return {
    scale: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    ellipse: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    createLinearGradient: vi.fn(gradient),
    createRadialGradient: vi.fn(gradient),
    getImageData: vi.fn((_x: number, _y: number, width: number, height: number) => ({
      width,
      height,
    })),
    fillStyle: '' as unknown,
    strokeStyle: '' as unknown,
    lineWidth: 0,
    lineJoin: '',
    shadowColor: '',
    shadowBlur: 0,
    shadowOffsetY: 0,
  };
}

class FakePath2D {
  constructor(readonly d: string) {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('drawPin', () => {
  it('draws the gold rim, the emerald drop and the khatam, sharp at twice its size', () => {
    vi.stubGlobal('Path2D', FakePath2D);
    const context = pinContext();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as RenderingContext
    );
    const pin = drawPin() as ImageData;
    expect([pin.width, pin.height]).toEqual([
      PIN_WIDTH * PIN_PIXEL_RATIO,
      PIN_HEIGHT * PIN_PIXEL_RATIO,
    ]);
    expect(context.scale).toHaveBeenCalledWith(PIN_PIXEL_RATIO, PIN_PIXEL_RATIO);
    // The rim and the drop are filled; the two squares of the khatam are stroked.
    const filled = context.fill.mock.calls.map(([path]) => (path as FakePath2D | undefined)?.d);
    expect(filled.filter(Boolean)).toHaveLength(2);
    expect(context.stroke).toHaveBeenCalledTimes(2);
    // A shadow lifts the rim, and is put away before the rest is drawn.
    expect(context.save).toHaveBeenCalledBefore(context.restore);
  });

  it('draws nothing where a canvas cannot: no Path2D, or no 2D context', () => {
    expect(drawPin()).toBeNull();
    vi.stubGlobal('Path2D', FakePath2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    expect(drawPin()).toBeNull();
  });
});
