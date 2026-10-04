import { describe, expect, it } from 'vitest';
import { containFrame, coverPlacement, gridCell, isRatio, labelSides } from './scene-geometry';

const PORTRAIT = { width: 1200, height: 1600 };

describe('coverPlacement', () => {
  it('uses the ratios as they are before the box is measured', () => {
    expect(coverPlacement({ x: 0.25, y: 0.5 }, PORTRAIT, null)).toEqual({
      left: 25,
      top: 50,
      visible: true,
    });
    expect(coverPlacement({ x: 0.25, y: 0.5 }, PORTRAIT, { width: 0, height: 100 }).left).toBe(25);
    expect(
      coverPlacement({ x: 0.25, y: 0.5 }, { width: 0, height: 0 }, { width: 10, height: 10 }).top
    ).toBe(50);
  });

  it('maps through a crop of the sides', () => {
    // A 3:4 photo in a 1:2 box: scaled to the box height, the sides are cut.
    const box = { width: 400, height: 800 };
    const centre = coverPlacement({ x: 0.5, y: 0.5 }, PORTRAIT, box);
    expect(centre).toEqual({ left: 50, top: 50, visible: true });
    const nearEdge = coverPlacement({ x: 0.1, y: 0.5 }, PORTRAIT, box);
    expect(nearEdge.visible).toBe(false);
    const inside = coverPlacement({ x: 0.3, y: 0.25 }, PORTRAIT, box);
    expect(inside.left).toBeCloseTo(((400 - 600) / 2 + 0.3 * 600) / 4, 6);
    expect(inside.top).toBeCloseTo(25, 6);
    expect(inside.visible).toBe(true);
  });

  it('maps through a crop of the top and bottom', () => {
    const box = { width: 900, height: 600 };
    expect(coverPlacement({ x: 0.5, y: 0.02 }, PORTRAIT, box).visible).toBe(false);
    expect(coverPlacement({ x: 0.5, y: 0.98 }, PORTRAIT, box).visible).toBe(false);
    expect(coverPlacement({ x: 0, y: 0.5 }, PORTRAIT, box)).toEqual({
      left: 0,
      top: 50,
      visible: true,
    });
  });
});

describe('labelSides', () => {
  it('hangs the label below in the upper half and above in the lower half', () => {
    expect(labelSides({ left: 50, top: 40, visible: true })).toEqual({
      horizontal: 'center',
      vertical: 'below',
    });
    expect(labelSides({ left: 50, top: 60, visible: true }).vertical).toBe('above');
  });

  it('grows the label toward the middle near a side', () => {
    expect(labelSides({ left: 10, top: 40, visible: true }).horizontal).toBe('toRight');
    expect(labelSides({ left: 90, top: 40, visible: true }).horizontal).toBe('toLeft');
  });
});

describe('gridCell and isRatio', () => {
  it('names the third of the photo a point is in', () => {
    expect(gridCell({ x: 0, y: 0 })).toEqual({ row: 0, column: 0 });
    expect(gridCell({ x: 0.5, y: 0.5 })).toEqual({ row: 1, column: 1 });
    expect(gridCell({ x: 1, y: 1 })).toEqual({ row: 2, column: 2 });
  });

  it('accepts 0 to 1 and nothing else', () => {
    expect([0, 0.5, 1].every(isRatio)).toBe(true);
    expect([-0.01, 1.01, Number.NaN, Number.POSITIVE_INFINITY].some(isRatio)).toBe(false);
  });
});

describe('containFrame', () => {
  it('fits the whole photo inside the box and centres it', () => {
    // A 4:3 photo in a square box: full width, three quarters of the height, centred.
    expect(containFrame({ width: 800, height: 600 }, { width: 400, height: 400 })).toEqual({
      left: 0,
      top: 12.5,
      width: 100,
      height: 75,
    });
    // A tall photo in a wide box: full height, a narrow strip in the middle.
    expect(containFrame({ width: 300, height: 600 }, { width: 600, height: 300 })).toEqual({
      left: 37.5,
      top: 0,
      width: 25,
      height: 100,
    });
  });

  it('takes the whole box before it is measured, or when a size is unusable', () => {
    const whole = { left: 0, top: 0, width: 100, height: 100 };
    expect(containFrame({ width: 800, height: 600 }, null)).toEqual(whole);
    expect(containFrame({ width: 800, height: 600 }, { width: 0, height: 10 })).toEqual(whole);
    expect(containFrame({ width: 800, height: 600 }, { width: 10, height: 0 })).toEqual(whole);
    expect(containFrame({ width: 0, height: 600 }, { width: 10, height: 10 })).toEqual(whole);
    expect(containFrame({ width: 800, height: 0 }, { width: 10, height: 10 })).toEqual(whole);
  });
});
