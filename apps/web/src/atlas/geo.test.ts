import { describe, expect, it } from 'vitest';
import {
  bearingDegrees,
  cameraHeading,
  distanceMeters,
  inView,
  normalizeDegrees,
  RADIUS_MAX_M,
  RADIUS_MIN_M,
  refetchDistance,
  relativeAngle,
  roundedDistance,
  searchRadius,
  sectorOf,
  smoothHeading,
  windowAround,
} from './geo';

const TUNIS = [10.1815, 36.8065] as const;
const CARTHAGE = [10.3233, 36.8528] as const;

describe('distances and bearings', () => {
  it('measures the great circle and points the way', () => {
    expect(distanceMeters(TUNIS, TUNIS)).toBe(0);
    expect(distanceMeters(TUNIS, CARTHAGE)).toBeGreaterThan(13_000);
    expect(distanceMeters(TUNIS, CARTHAGE)).toBeLessThan(14_500);
    expect(bearingDegrees(TUNIS, CARTHAGE)).toBeGreaterThan(60);
    expect(bearingDegrees(TUNIS, CARTHAGE)).toBeLessThan(70);
    expect(bearingDegrees([0, 0], [0, 1])).toBe(0);
    expect(bearingDegrees([0, 0], [1, 0])).toBeCloseTo(90);
    expect(bearingDegrees([0, 0], [0, -1])).toBeCloseTo(180);
    expect(bearingDegrees([0, 0], [-1, 0])).toBeCloseTo(270);
    // Antipodes: the haversine argument is clamped, never NaN.
    expect(distanceMeters([0, 0], [180, 0])).toBeCloseTo(Math.PI * 6_371_000, -3);
  });

  it('folds angles into one turn', () => {
    expect(normalizeDegrees(370)).toBe(10);
    expect(normalizeDegrees(-10)).toBe(350);
    expect(normalizeDegrees(0)).toBe(0);
  });
});

describe('the search window', () => {
  it('grows with a poor fix and with widening, inside the caps', () => {
    expect(searchRadius(null)).toBe(RADIUS_MIN_M);
    expect(searchRadius(100)).toBe(RADIUS_MIN_M);
    expect(searchRadius(2_000)).toBe(4_000);
    expect(searchRadius(2_000, 1)).toBe(8_000);
    expect(searchRadius(2_000, 5)).toBe(RADIUS_MAX_M);
  });

  it('frames the point and wraps at the antimeridian and the poles', () => {
    const around = windowAround(TUNIS, 1_500);
    expect(around.west).toBeLessThan(TUNIS[0]);
    expect(around.east).toBeGreaterThan(TUNIS[0]);
    expect(around.south).toBeLessThan(TUNIS[1]);
    expect(around.north).toBeGreaterThan(TUNIS[1]);
    expect(around.north - around.south).toBeCloseTo(0.027, 3);

    const edge = windowAround([179.99, 0], 5_000);
    expect(edge.west).toBeGreaterThan(0);
    expect(edge.east).toBeLessThan(0);

    const pole = windowAround([0, 89.99], 5_000);
    expect(pole.north).toBe(90);
    expect(pole.east - pole.west).toBeLessThanOrEqual(360);
  });

  it('asks again only after a real move', () => {
    expect(refetchDistance(1_500)).toBe(375);
    expect(refetchDistance(400)).toBe(250);
  });
});

describe('the distance label', () => {
  it('says nothing finer than the cell, then rounds to its coarseness', () => {
    expect(roundedDistance(400, 1_000)).toBeNull();
    expect(roundedDistance(1_240, 1_000)).toBe(1_000);
    expect(roundedDistance(1_760, 1_000)).toBe(2_000);
    expect(roundedDistance(330, 100)).toBe(300);
  });
});

describe('direction', () => {
  it('measures the turn from the heading to the bearing, right positive', () => {
    expect(relativeAngle(90, 0)).toBe(90);
    expect(relativeAngle(0, 90)).toBe(-90);
    expect(relativeAngle(10, 350)).toBe(20);
    expect(relativeAngle(180, 0)).toBe(180);
  });

  it('names four sectors', () => {
    expect(sectorOf(0)).toBe('ahead');
    expect(sectorOf(-45)).toBe('ahead');
    expect(sectorOf(90)).toBe('right');
    expect(sectorOf(-90)).toBe('left');
    expect(sectorOf(170)).toBe('behind');
  });

  it('enters the view inside 30 degrees and leaves beyond 40', () => {
    expect(inView(false, 25)).toBe(true);
    expect(inView(false, 35)).toBe(false);
    expect(inView(true, 35)).toBe(true);
    expect(inView(true, -45)).toBe(false);
  });

  it('smooths the heading around the circle', () => {
    expect(smoothHeading(null, 370)).toBe(10);
    expect(smoothHeading(350, 10)).toBe(355);
    expect(smoothHeading(10, 350)).toBe(5);
    expect(smoothHeading(0, 100, 1)).toBe(100);
  });
});

describe('the camera heading from the sensors', () => {
  const reading = (alpha: number | null, beta: number | null, gamma: number | null) => ({
    alpha,
    beta,
    gamma,
    absolute: true,
  });

  it('turns absolute Euler angles into where the back camera points', () => {
    // Upright, screen toward the holder, camera to the north.
    expect(cameraHeading(reading(0, 90, 0))).toBeCloseTo(0);
    // Turned to face east (alpha counts counter-clockwise).
    expect(cameraHeading(reading(270, 90, 0))).toBeCloseTo(90);
    expect(cameraHeading(reading(180, 90, 0))).toBeCloseTo(180);
    expect(cameraHeading(reading(90, 90, 0))).toBeCloseTo(270);
    // Tilted a little keeps the same answer.
    expect(cameraHeading(reading(270, 70, 0))).toBeCloseTo(90);
    // Missing tilt angles are read as zero.
    expect(cameraHeading(reading(0, null, null))).toBeNull();
  });

  it('refuses a relative alpha, a missing alpha and a camera that looks at the ground', () => {
    expect(cameraHeading({ alpha: 10, beta: 90, gamma: 0, absolute: false })).toBeNull();
    expect(cameraHeading(reading(null, 90, 0))).toBeNull();
    expect(cameraHeading(reading(0, 0, 0))).toBeNull();
  });

  it('prefers the compass heading Safari gives, turned by the screen', () => {
    expect(
      cameraHeading({ alpha: 5, beta: 0, gamma: 0, absolute: false, webkitCompassHeading: 350 })
    ).toBe(350);
    expect(
      cameraHeading(
        { alpha: null, beta: null, gamma: null, absolute: false, webkitCompassHeading: 350 },
        90
      )
    ).toBe(80);
    expect(
      cameraHeading({ alpha: 0, beta: 90, gamma: 0, absolute: true, webkitCompassHeading: null })
    ).toBeCloseTo(0);
  });
});
