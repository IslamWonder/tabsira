import { describe, expect, it } from 'vitest';
import { coarsen, lngLatOf } from './types';

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
