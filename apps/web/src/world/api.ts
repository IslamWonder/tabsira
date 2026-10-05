import { api } from '@/lib/api/client';
import { attempt, type Result } from '@/lib/api/result';
import type { components } from '@/lib/api/schema';

export type World = components['schemas']['WorldOut'];
export type Region = components['schemas']['RegionOut'];
export type Place = components['schemas']['WorldPlaceOut'];
export type PlaceInsight = components['schemas']['PlaceInsightOut'];
export type Relation = components['schemas']['RelationOut'];
export type Treasure = components['schemas']['TreasureOut'];
export type Reveal = components['schemas']['RevealOut'];
export type WorldTheme = components['schemas']['WorldTheme'];

/** The map: every region with its fog, the places that came out of it, the threads. */
export function loadWorld(): Promise<Result<World>> {
  return attempt(api.GET('/world'));
}

/** The reveals whose effect the world just played: it never plays them again, on any device. */
export function markRevealsShown(ids: readonly string[]): Promise<Result<unknown>> {
  return attempt(api.POST('/world/reveals/shown', { body: { ids: [...ids] } }));
}

/** Opening a place is recorded, and a treasure that is ready comes back on it. */
export function visitPlace(placeId: string): Promise<Result<Place>> {
  return attempt(
    api.POST('/world/places/{place_id}/visit', { params: { path: { place_id: placeId } } })
  );
}

/** The treasure's verified text, from the store; refused until the return. */
export function revealTreasure(treasureId: string): Promise<Result<Treasure>> {
  return attempt(
    api.POST('/world/treasures/{treasure_id}/reveal', {
      params: { path: { treasure_id: treasureId } },
    })
  );
}
