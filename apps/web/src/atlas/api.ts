import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type {
  AtlasEntry,
  AtlasFeatureCollection,
  AtlasFilters,
  AtlasPlace,
  CapturePointIn,
  MapEntryOwner,
  PlaceHit,
  Window,
} from './types';

/*
 * Every call of the atlas, typed by the generated client. The browser sends a
 * map window and filters, never the visitor's own position: the near-me button only
 * moves the map, and what the API then receives is the window it shows.
 */

const PERIOD_DAYS = { week: 7, month: 30, year: 365 } as const;

function sinceOf(filters: AtlasFilters, now: () => number): string | undefined {
  if (filters.period === 'all') {
    return undefined;
  }
  return new Date(now() - PERIOD_DAYS[filters.period] * 86_400_000).toISOString();
}

export function entriesIn(
  window: Window,
  filters: AtlasFilters,
  now: () => number = Date.now
): Promise<Result<AtlasFeatureCollection>> {
  return attempt(
    api.GET('/atlas/entries', {
      params: {
        query: {
          west: window.west,
          south: window.south,
          east: window.east,
          north: window.north,
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
