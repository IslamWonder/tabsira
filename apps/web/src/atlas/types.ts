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
export type AtlasEntry = Schemas['AtlasEntryOut'];
export type AtlasPlace = Schemas['AtlasPlaceOut'];
export type PlaceRef = Schemas['PlaceRef'];
export type MapEntryOwner = Schemas['MapEntryOwnerOut'];
export type CapturePointIn = Schemas['CapturePointIn'];
export type LocationSource = Schemas['LocationSource'];
export type LocationMeaning = Schemas['LocationMeaning'];
export type PlaceHit = Schemas['PlaceHit'];

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

export type Period = 'all' | 'week' | 'month' | 'year';

export interface AtlasFilters {
  period: Period;
  country: string | null;
  concept: string | null;
}

export const EMPTY_FILTERS: AtlasFilters = { period: 'all', country: null, concept: null };

/**
 * The map tiles (decision 9): OpenFreeMap, the one third-party request a
 * visitor's browser makes besides consented analytics, named on the terms page.
 */
export const MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

/** Where the map opens for a newcomer: centred on the Arab world, zoomed out. */
export const DEFAULT_VIEW = { center: [30, 27] as [number, number], zoom: 2.6 };
