import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import {
  type AtlasEntry,
  type AtlasFeatureCollection,
  type AtlasFilters,
  type AtlasOrphans,
  type AtlasPlace,
  type CapturePointIn,
  coarsen,
  coarsePoint,
  type MapEntryOwner,
  ORPHAN_PAGE,
  ORPHAN_RADIUS_M,
  type PlaceHit,
  type Sponsorship,
  type Window,
} from './types';

/*
 * Every call of the atlas, typed by the generated client. The browser sends a
 * map window and filters, never the visitor's own position: the near-me button only
 * moves the map, and what the API then receives is the window it shows.
 */

const PERIOD_DAYS = { week: 7, month: 30, year: 365 } as const;

/** The first day of the period, as a day: the API takes days, never times. */
function sinceOf(filters: AtlasFilters, now: () => number): string | undefined {
  if (filters.period === 'all') {
    return undefined;
  }
  return new Date(now() - PERIOD_DAYS[filters.period] * 86_400_000).toISOString().slice(0, 10);
}

export function entriesIn(
  window: Window,
  filters: AtlasFilters,
  now: () => number = Date.now
): Promise<Result<AtlasFeatureCollection>> {
  const wide = coarsen(window);
  return attempt(
    api.GET('/atlas/entries', {
      params: {
        query: {
          west: wide.west,
          south: wide.south,
          east: wide.east,
          north: wide.north,
          since: sinceOf(filters, now),
          country: filters.country ?? undefined,
          concept: filters.concept ?? undefined,
        },
      },
    })
  );
}

export function getEntry(entryId: string): Promise<Result<AtlasEntry>> {
  return attempt(api.GET('/atlas/entries/{entry_id}', { params: { path: { entry_id: entryId } } }));
}

export function getPlace(geonameId: number, cursor: string | null): Promise<Result<AtlasPlace>> {
  return attempt(
    api.GET('/atlas/places/{geoname_id}', {
      params: { path: { geoname_id: geonameId }, query: cursor === null ? {} : { cursor } },
    })
  );
}

export function searchPlaces(q: string): Promise<Result<PlaceHit[]>> {
  return attempt(api.GET('/geo/search', { params: { query: { q, limit: 6 } } }));
}

export function myEntry(insightId: string): Promise<Result<MapEntryOwner>> {
  return attempt(
    api.GET('/insights/{insight_id}/map', { params: { path: { insight_id: insightId } } })
  );
}

export function placeInsight(
  insightId: string,
  body: CapturePointIn
): Promise<Result<MapEntryOwner>> {
  return attempt(
    api.PUT('/insights/{insight_id}/map', { params: { path: { insight_id: insightId } }, body })
  );
}

export function publishEntry(insightId: string): Promise<Result<MapEntryOwner>> {
  return attempt(
    api.POST('/insights/{insight_id}/map/publish', { params: { path: { insight_id: insightId } } })
  );
}

export function withdrawEntry(insightId: string): Promise<Result<unknown>> {
  return attempt(
    api.DELETE('/insights/{insight_id}/map', { params: { path: { insight_id: insightId } } })
  );
}

export function myEntries(): Promise<Result<MapEntryOwner[]>> {
  return attempt(api.GET('/me/map-entries'));
}

/** Orphaned entries near a position; the position is snapped to the grid here, so no caller can send a finer one. */
export function orphansNear(
  point: readonly [number, number],
  cursor: string | null
): Promise<Result<AtlasOrphans>> {
  const [lng, lat] = coarsePoint(point);
  return attempt(
    api.GET('/atlas/orphans', {
      params: {
        query: {
          lat,
          lng,
          radius: ORPHAN_RADIUS_M,
          limit: ORPHAN_PAGE,
          ...(cursor === null ? {} : { cursor }),
        },
      },
    })
  );
}

export function sponsorEntry(entryId: string): Promise<Result<Sponsorship>> {
  return attempt(
    api.PUT('/atlas/entries/{entry_id}/sponsorship', { params: { path: { entry_id: entryId } } })
  );
}

export function endSponsorship(entryId: string): Promise<Result<unknown>> {
  return attempt(
    api.DELETE('/atlas/entries/{entry_id}/sponsorship', {
      params: { path: { entry_id: entryId } },
    })
  );
}

export function writeReflection(entryId: string, reflection: string): Promise<Result<Sponsorship>> {
  return attempt(
    api.PUT('/atlas/entries/{entry_id}/sponsorship/reflection', {
      params: { path: { entry_id: entryId } },
      body: { reflection },
    })
  );
}

export function mySponsorships(): Promise<Result<Sponsorship[]>> {
  return attempt(api.GET('/me/sponsorships'));
}
