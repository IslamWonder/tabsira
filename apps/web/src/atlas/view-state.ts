import type { Route } from 'next';
import { type AtlasFilters, EMPTY_FILTERS, type Period } from './types';

/*
 * What the atlas is looking at, carried in the address's fragment: the centre
 * and zoom of the map, the selected entry and the filters (extension §4: the
 * camera's show-on-map link opens the same view; coming back restores it).
 * A fragment never leaves the browser, so a centre near a person stays on the
 * device; it is also rounded, since a map centre needs no finer than that.
 */

export interface AtlasView {
  center: [number, number];
  zoom: number;
}

export interface AtlasViewState {
  view: AtlasView | null;
  selected: string | null;
  filters: AtlasFilters;
}

export const EMPTY_VIEW_STATE: AtlasViewState = {
  view: null,
  selected: null,
  filters: EMPTY_FILTERS,
};

const PERIODS: readonly Period[] = ['all', 'week', 'month', 'year'];
const PUBLIC_ID = /^[1-9][0-9]{0,18}$/;
const COUNTRY = /^[A-Z]{2}$/;
const CONCEPT = /^[A-Za-z0-9_.:-]{1,64}$/;
const ZOOM_MIN = 2;
const ZOOM_MAX = 16;

function round(value: number, decimals: number): number {
  return Number(value.toFixed(decimals));
}

/** The fragment for a state, with the `#`, or an empty string when there is nothing to carry. */
export function encodeViewHash(state: AtlasViewState): string {
  const parts: string[] = [];
  if (state.view !== null) {
    const [lng, lat] = state.view.center;
    parts.push(`c=${round(lng, 3)},${round(lat, 3)},${round(state.view.zoom, 1)}`);
  }
  if (state.selected !== null) {
    parts.push(`e=${state.selected}`);
  }
  if (state.filters.period !== 'all') {
    parts.push(`p=${state.filters.period}`);
  }
  if (state.filters.country !== null) {
    parts.push(`k=${state.filters.country}`);
  }
  if (state.filters.concept !== null) {
    parts.push(`t=${state.filters.concept}`);
  }
  return parts.length === 0 ? '' : `#${parts.join('&')}`;
}

function parseView(value: string | null): AtlasView | null {
  if (value === null) {
    return null;
  }
  const numbers = value.split(',').map(Number);
  const [lng, lat, zoom] = numbers;
  if (
    numbers.length !== 3 ||
    lng === undefined ||
    lat === undefined ||
    zoom === undefined ||
    !numbers.every(Number.isFinite) ||
    Math.abs(lng) > 180 ||
    Math.abs(lat) > 90
  ) {
    return null;
  }
  return { center: [lng, lat], zoom: Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom)) };
}

/** Reads a fragment back; anything malformed is simply absent. */
export function parseViewHash(hash: string): AtlasViewState {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const period = params.get('p');
  const country = params.get('k');
  const concept = params.get('t');
  const selected = params.get('e');
  return {
    view: parseView(params.get('c')),
    selected: selected !== null && PUBLIC_ID.test(selected) ? selected : null,
    filters: {
      period: PERIODS.find((candidate) => candidate === period) ?? 'all',
      country: country !== null && COUNTRY.test(country) ? country : null,
      concept: concept !== null && CONCEPT.test(concept) ? concept : null,
    },
  };
}

/** The atlas page looking at a state. */
export function atlasHref(state: AtlasViewState): Route {
  return `/atlas${encodeViewHash(state)}` as Route;
}

/** The width a phone's map is assumed to show, in pixels, when a radius is turned into a zoom. */
const VIEWPORT_PX = 360;
const METERS_PER_PIXEL_AT_ZERO = 156_543.03392;

/** The zoom at which a circle of `radiusM` around a latitude fills a phone's map. */
export function zoomForRadius(radiusM: number, latitude: number): number {
  const cosLat = Math.max(0.01, Math.cos((latitude * Math.PI) / 180));
  const zoom = Math.log2((METERS_PER_PIXEL_AT_ZERO * cosLat * VIEWPORT_PX) / (2 * radiusM));
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, round(zoom, 1)));
}
