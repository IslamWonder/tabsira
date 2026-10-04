import type { Window } from './types';

/*
 * The arithmetic of the camera discovery, all of it on the device (extension
 * §7): distances and bearings from the device to the published points, the
 * window asked of the atlas around the device, and the heading of the back
 * camera from the orientation sensors. Nothing here reaches the server; the
 * one request made is the window, widened to the atlas grid as every window is.
 */

/** A point as GeoJSON orders it: [longitude, latitude]. */
export type LngLat = readonly [number, number];

const EARTH_RADIUS_M = 6_371_000;
const RAD = Math.PI / 180;

/** Great-circle distance in metres (haversine). */
export function distanceMeters(from: LngLat, to: LngLat): number {
  const dLat = (to[1] - from[1]) * RAD;
  const dLng = (to[0] - from[0]) * RAD;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(from[1] * RAD) * Math.cos(to[1] * RAD) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Initial bearing from `from` to `to`, clockwise from north, in [0, 360). */
export function bearingDegrees(from: LngLat, to: LngLat): number {
  const lat1 = from[1] * RAD;
  const lat2 = to[1] * RAD;
  const dLng = (to[0] - from[0]) * RAD;
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return normalizeDegrees(Math.atan2(y, x) / RAD);
}

/** Folds an angle into [0, 360). */
export function normalizeDegrees(degrees: number): number {
  const folded = degrees % 360;
  return folded < 0 ? folded + 360 : folded;
}

/** The search radius: never tighter than the fix's own error, never wider than the cap. */
export const RADIUS_MIN_M = 1_500;
export const RADIUS_MAX_M = 20_000;
/** Each widening doubles the radius, up to the cap. */
export const RADIUS_WIDEN_FACTOR = 2;

export function searchRadius(accuracyM: number | null, widened = 0): number {
  const base = Math.max(RADIUS_MIN_M, accuracyM === null ? 0 : accuracyM * 2);
  return Math.min(RADIUS_MAX_M, base * RADIUS_WIDEN_FACTOR ** widened);
}

/**
 * The window of `radiusM` around a point, in degrees; longitudes wrap so a
 * window at the antimeridian keeps `west > east`, as the API reads it.
 */
export function windowAround(center: LngLat, radiusM: number): Window {
  const dLat = radiusM / EARTH_RADIUS_M / RAD;
  const cosLat = Math.max(0.01, Math.cos(center[1] * RAD));
  const dLng = Math.min(180, dLat / cosLat);
  const wrap = (lng: number) => ((((lng + 180) % 360) + 360) % 360) - 180;
  return {
    west: wrap(center[0] - dLng),
    south: Math.max(-90, center[1] - dLat),
    east: wrap(center[0] + dLng),
    north: Math.min(90, center[1] + dLat),
  };
}

/**
 * How far the device may drift before the atlas is asked again: a quarter of
 * the radius, and never less than 250 m, so a fix that wanders does not ask
 * on every reading (extension §7).
 */
export function refetchDistance(radiusM: number): number {
  return Math.max(250, radiusM / 4);
}

/**
 * The distance label's number, or null inside the entry's own cell: a point
 * is a cell centre, so a distance shorter than the cell says nothing true.
 * Beyond it the distance is rounded to the cell's own coarseness.
 */
export function roundedDistance(distanceM: number, cellM: number): number | null {
  if (distanceM < cellM) {
    return null;
  }
  const step = Math.max(100, cellM / 2);
  return Math.round(distanceM / step) * step;
}

/** The signed angle from the heading to a bearing, in (-180, 180]: positive is to the right. */
export function relativeAngle(bearing: number, heading: number): number {
  const delta = normalizeDegrees(bearing - heading);
  return delta > 180 ? delta - 360 : delta;
}

export type Sector = 'ahead' | 'right' | 'behind' | 'left';

/** Four words for a relative angle; the arrow carries the exact value. */
export function sectorOf(relative: number): Sector {
  const angle = Math.abs(relative);
  if (angle <= 45) {
    return 'ahead';
  }
  if (angle >= 135) {
    return 'behind';
  }
  return relative > 0 ? 'right' : 'left';
}

/** Enter the field of view inside ±30°, leave it beyond ±40°: no label flickers at the edge. */
export const IN_VIEW_ENTER = 30;
export const IN_VIEW_EXIT = 40;

export function inView(wasInView: boolean, relative: number): boolean {
  const angle = Math.abs(relative);
  return wasInView ? angle <= IN_VIEW_EXIT : angle <= IN_VIEW_ENTER;
}

/** Exponential smoothing on the circle: a fraction of the way from `previous` to `next`. */
export function smoothHeading(previous: number | null, next: number, factor = 0.25): number {
  if (previous === null) {
    return normalizeDegrees(next);
  }
  return normalizeDegrees(previous + relativeAngle(next, previous) * factor);
}

/** The three Euler angles of a DeviceOrientationEvent, as the browser gives them. */
export interface OrientationReading {
  alpha: number | null;
  beta: number | null;
  gamma: number | null;
  absolute: boolean;
  /** Safari's compass heading of the device's top edge, when it has one. */
  webkitCompassHeading?: number | null;
}

/**
 * Where the back camera points, clockwise from north, or null when the
 * reading is not anchored to north (a relative alpha is a rotation since the
 * page loaded, never a geographic heading: extension §6 B). Chrome gives
 * absolute Euler angles; the camera's direction is the device's -z axis
 * turned by them (the rotation matrix of the DeviceOrientation specification),
 * so holding the phone upright or flat gives the same answer. Safari gives the
 * heading of the top edge instead; the screen's rotation turns it toward the camera.
 */
export function cameraHeading(reading: OrientationReading, screenAngle = 0): number | null {
  const webkit = reading.webkitCompassHeading;
  if (typeof webkit === 'number' && Number.isFinite(webkit)) {
    return normalizeDegrees(webkit + screenAngle);
  }
  if (!reading.absolute || reading.alpha === null) {
    return null;
  }
  const z = reading.alpha * RAD;
  const x = (reading.beta ?? 0) * RAD;
  const y = (reading.gamma ?? 0) * RAD;
  const vx = -Math.cos(z) * Math.sin(y) - Math.sin(z) * Math.sin(x) * Math.cos(y);
  const vy = -Math.sin(z) * Math.sin(y) + Math.cos(z) * Math.sin(x) * Math.cos(y);
  if (Math.abs(vx) < 1e-9 && Math.abs(vy) < 1e-9) {
    // The camera looks straight up or down: no direction on the ground to name.
    return null;
  }
  return normalizeDegrees(Math.atan2(vx, vy) / RAD);
}
