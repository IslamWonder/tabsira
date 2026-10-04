import { describe, expect, it } from 'vitest';
import { KHATAM_RATIO, starPoints } from './geometry';

describe('starPoints', () => {
  it('alternates outer and inner radius, starting at the top', () => {
    const points = starPoints(10, 10, 10, 5, 4).split(' ');
    expect(points).toHaveLength(8);
    expect(points[0]).toBe('10.00,0.00');
    expect(points[2]).toBe('20.00,10.00');
  });

  it('draws eight points by default with the khatam ratio', () => {
    expect(starPoints(0, 0, 1, KHATAM_RATIO).split(' ')).toHaveLength(16);
    expect(starPoints(0, 0, 1, 0.5, 8, 0).split(' ')[0]).toBe('1.00,0.00');
  });
});
