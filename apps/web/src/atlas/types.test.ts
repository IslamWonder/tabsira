import { describe, expect, it } from 'vitest';
import { coarsen, coarsePoint, lngLatOf } from './types';

describe('lngLatOf', () => {
  it('reads a GeoJSON point in [longitude, latitude] order and treats zero as a value', () => {
    expect(lngLatOf({ coordinates: [10.18, 0] })).toEqual([10.18, 0]);
    expect(lngLatOf({ coordinates: [] })).toEqual([0, 0]);
  });
});

describe('coarsen', () => {
  it('widens a window outward to the grid and clamps it to the globe', () => {
    expect(coarsen({ west: 10.181, south: 36.806, east: 10.182, north: 36.807 })).toEqual({
      west: 10.15,
      south: 36.8,
      east: 10.2,
      north: 36.85,
    });
    expect(coarsen({ west: -180.01, south: -90.01, east: 180.01, north: 90.01 })).toEqual({
      west: -180,
      south: -90,
      east: 180,
      north: 90,
    });
  });
});

describe('coarsePoint', () => {
  it('snaps a position to the 0.05 degree grid, as [longitude, latitude], and clamps it to the globe', () => {
    expect(coarsePoint([10.18153, 36.80651])).toEqual([10.2, 36.8]);
    expect(coarsePoint([-0.0049, 0.0251])).toEqual([0, 0.05]);
    expect(coarsePoint([180.2, -90.4])).toEqual([180, -90]);
  });
});
