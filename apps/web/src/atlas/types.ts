import type { components } from '@/lib/api/schema';

/*
 * The shapes of the world atlas, from the API's OpenAPI document. The
 * public ones carry the published point alone; only the owner's entry carries
 * a capture point, and only to its owner.
 */

type Schemas = components['schemas'];

export type AtlasFeature = Schemas['AtlasFeature'];
export type AtlasFeatureProperties = Schemas['AtlasFeatureProperties'];
export type AtlasFeatureCollection = Schemas['AtlasFeatureCollection'];
export type AtlasClusterCollection = Schemas['AtlasClusterCollection'];
export type AtlasClusterFeature = Schemas['AtlasClusterFeature'];
export type AtlasEntriesPage = Schemas['AtlasEntriesPage'];

/** What the map draws: a group of entries, or one entry. */
export type MapFeature = AtlasFeature | AtlasClusterFeature;

/** Whether a drawn feature is a group (the server's `kind`); an entry from an older route has none. */
export function isCluster(feature: MapFeature): feature is AtlasClusterFeature {
  return 'kind' in feature.properties && feature.properties.kind === 'cluster';
}
export type AtlasEntry = Schemas['AtlasEntryOut'];
export type AtlasPlace = Schemas['AtlasPlaceOut'];
export type PlaceRef = Schemas['PlaceRef'];
export type MapEntryOwner = Schemas['MapEntryOwnerOut'];
export type CapturePointIn = Schemas['CapturePointIn'];
export type LocationSource = Schemas['LocationSource'];
export type LocationMeaning = Schemas['LocationMeaning'];
export type PlaceHit = Schemas['PlaceHit'];
export type AtlasOrphans = Schemas['AtlasOrphansOut'];
export type Sponsorship = Schemas['SponsorshipOut'];

/** The two numbers of a GeoJSON point as a pair: [longitude, latitude]. */
export function lngLatOf(point: { coordinates: number[] }): [number, number] {
  return [point.coordinates[0] ?? 0, point.coordinates[1] ?? 0];
}

/** A map window in degrees; `west > east` crosses the antimeridian. */
export interface Window {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** The grid a window is widened to before it is sent, so a request never says where a person stands to the metre. */
export const WINDOW_STEP = 0.05;

/** Widens the window outward to the grid: what the API (and its logs) receive is never finer than that. */
export function coarsen(window: Window): Window {
  const down = (value: number) => Math.floor(value / WINDOW_STEP) * WINDOW_STEP;
  const up = (value: number) => Math.ceil(value / WINDOW_STEP) * WINDOW_STEP;
  const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));
  return {
    west: clamp(Number(down(window.west).toFixed(2)), 180),
    south: clamp(Number(down(window.south).toFixed(2)), 90),
    east: clamp(Number(up(window.east).toFixed(2)), 180),
    north: clamp(Number(up(window.north).toFixed(2)), 90),
  };
}

/**
 * The window widened by `ratio` of its size on every side, so groups near the edges are
 * counted whole. Crosses the antimeridian when `west > east`; a window that would cover the
 * world is the world.
 */
export function padWindow(window: Window, ratio: number): Window {
  const crossing = window.west > window.east;
  const width = crossing ? window.east - window.west + 360 : window.east - window.west;
  const height = window.north - window.south;
  const south = Math.max(-90, window.south - height * ratio);
  const north = Math.min(90, window.north + height * ratio);
  if (width * (1 + 2 * ratio) >= 360) {
    return { west: -180, south, east: 180, north };
  }
  const wrap = (value: number) => (value > 180 ? value - 360 : value < -180 ? value + 360 : value);
  return {
    west: wrap(window.west - width * ratio),
    south,
    east: wrap(window.east + width * ratio),
    north,
  };
}

/** How long a map stands still before the atlas asks for what it shows. */
export const MOVE_DEBOUNCE_MS = 250;
/** The share of the window added on each side when asking for groups. */
export const WINDOW_PADDING = 0.25;
/** Entries per page of the list beside the map. */
export const LIST_PAGE = 20;

/**
 * A position snapped to the same grid as a window, [longitude, latitude]: the
 * orphans request carries this and never the exact point. The API does not round it.
 */
export function coarsePoint(point: readonly [number, number]): [number, number] {
  const snap = (value: number, limit: number) =>
    Math.max(
      -limit,
      Math.min(limit, Number((Math.round(value / WINDOW_STEP) * WINDOW_STEP).toFixed(2)))
    );
  return [snap(point[0], 180), snap(point[1], 90)];
}

/** Orphaned entries sit at widened places (a city, a region, a country), so the search is wide. */
export const ORPHAN_RADIUS_M = 150_000;
export const ORPHAN_PAGE = 10;

export type Period = 'all' | 'week' | 'month' | 'year';

export interface AtlasFilters {
  period: Period;
  country: string | null;
  concept: string | null;
}

export const EMPTY_FILTERS: AtlasFilters = { period: 'all', country: null, concept: null };

/**
 * The map tiles (decision 9): OpenFreeMap, one of the third-party requests a
 * visitor's browser makes, named on the terms and privacy pages.
 */
export const MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

/** Where the map opens for a newcomer: centred on the Arab world, zoomed out. */
export const DEFAULT_VIEW = { center: [30, 27] as [number, number], zoom: 2.6 };
