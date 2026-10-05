import { describe, expect, it } from 'vitest';
import { FEATURE } from '@/test/atlas';
import { coarsen, coarsePoint, isCluster, lngLatOf, type MapFeature, padWindow } from './types';

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

describe('padWindow', () => {
  it('widens a window by a share of its size on every side', () => {
    expect(padWindow({ west: 10, south: 30, east: 20, north: 40 }, 0.25)).toEqual({
      west: 7.5,
      south: 27.5,
      east: 22.5,
      north: 42.5,
    });
  });

  it('stops at the poles, wraps over the antimeridian, and says the world when it would cover it', () => {
    expect(padWindow({ west: 170, south: 80, east: 179, north: 89 }, 0.25)).toEqual({
      west: 167.75,
      south: 77.75,
      east: -178.75,
      north: 90,
    });
    expect(padWindow({ west: 170, south: -89, east: -170, north: -80 }, 0.25)).toEqual({
      west: 165,
      south: -90,
      east: -165,
      north: -77.75,
    });
    expect(padWindow({ west: -170, south: 0, east: -165, north: 1 }, 0.25)).toEqual({
      west: -171.25,
      south: -0.25,
      east: -163.75,
      north: 1.25,
    });
    expect(padWindow({ west: -179, south: 0, east: 178, north: 1 }, 0.25)).toEqual({
      west: -180,
      south: -0.25,
      east: 180,
      north: 1.25,
    });
    expect(padWindow({ west: -179.5, south: 0, east: -170, north: 1 }, 0.25)).toMatchObject({
      west: 178.125,
      east: -167.625,
    });
    expect(padWindow({ west: -170, south: 0, east: 170, north: 1 }, 0.25)).toMatchObject({
      west: -180,
      east: 180,
    });
  });
});

describe('isCluster', () => {
  it("tells a group from an entry, with or without the server's kind", () => {
    const group: MapFeature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [1, 2] },
      properties: { kind: 'cluster', id: 'c', count: 3, bbox: [0, 0, 1, 1] },
    };
    const entry: MapFeature = {
      ...FEATURE,
      properties: { ...FEATURE.properties, kind: 'entry' },
    } as MapFeature;
    expect([group, entry, FEATURE].map(isCluster)).toEqual([true, false, false]);
  });
});
