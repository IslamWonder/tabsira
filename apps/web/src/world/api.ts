import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type World = components['schemas']['WorldOut'];
export type Region = components['schemas']['RegionOut'];
// The API has two schemas named PlaceOut (the insight's and the world's); the world's is this one.
export type Place = components['schemas']['src__schemas__world__PlaceOut'];
export type PlaceInsight = components['schemas']['PlaceInsightOut'];
export type Relation = components['schemas']['RelationOut'];
export type Treasure = components['schemas']['TreasureOut'];

/**
 * Public ids travel as strings in every answer (decision 37: 64-bit numbers
 * that a JavaScript number cannot hold), but the OpenAPI document types a path
 * parameter as a number. The string goes into the path untouched.
 */
function pathId(id: string): number {
  return id as unknown as number;
}

/** The map: every region with its fog, the places that came out of it, the threads. */
export function loadWorld(): Promise<Result<World>> {
  return attempt(api.GET('/world'));
}

/** Opening a place is recorded, and a treasure that is ready comes back on it. */
export function visitPlace(placeId: string): Promise<Result<Place>> {
  return attempt(
    api.POST('/world/places/{place_id}/visit', { params: { path: { place_id: pathId(placeId) } } })
  );
}

/** The treasure's verified text, from the store; refused until the return. */
export function revealTreasure(treasureId: string): Promise<Result<Treasure>> {
  return attempt(
    api.POST('/world/treasures/{treasure_id}/reveal', {
      params: { path: { treasure_id: pathId(treasureId) } },
    })
  );
}
