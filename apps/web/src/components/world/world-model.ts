import type { Route } from 'next';
import { messages } from '@/messages';
import type { Place, Region, Relation, World } from '@/world/api';

/** A region of the fixed map with what the learner has made of it. */
export interface RegionView {
  region: Region;
  /** The place the fog left, or null while the region is under fog. */
  place: Place | null;
  /** A treasure is ready to be revealed here. */
  hasTreasure: boolean;
}

export function regionViews(world: World): RegionView[] {
  const places = new Map(world.places.map((place) => [place.id, place]));
  return world.regions.map((region) => {
    const place =
      region.fog || region.place_id === null ? null : (places.get(region.place_id) ?? null);
    return { region, place, hasTreasure: place?.treasure != null };
  });
}

/** A region's state in words: shared by the map's names and the list, so they never disagree. */
export function regionState(view: RegionView): string {
  const M = messages.world.list;
  if (view.place === null) {
    return M.fog;
  }
  const base =
    view.place.insights.length === 0 ? M.openedNoInsights : M.opened(view.place.insights.length);
  return view.hasTreasure ? M.withTreasure(base) : base;
}

export function openedCount(views: readonly RegionView[]): number {
  return views.filter((view) => view.place !== null).length;
}

/** A recorded relation between two opened places, with where its ends sit on the map. */
export interface Thread {
  key: string;
  relation: Relation;
  from: RegionView;
  to: RegionView;
}

/** Threads whose two places are both on the map; a relation to a place that is not shown is left out. */
export function threads(views: readonly RegionView[], relations: readonly Relation[]): Thread[] {
  const byPlace = new Map(
    views.flatMap((view) => (view.place === null ? [] : [[view.place.id, view] as const]))
  );
  return relations.flatMap((relation) => {
    const from = byPlace.get(relation.place_a_id);
    const to = byPlace.get(relation.place_b_id);
    return from && to
      ? [
          {
            key: `${relation.place_a_id}-${relation.place_b_id}-${relation.reason}`,
            relation,
            from,
            to,
          },
        ]
      : [];
  });
}

/**
 * The route of an insight's own screen, built by the scan and insight flow. The
 * typed-routes list only knows it once that route exists, hence the cast.
 */
export function insightHref(id: string): Route {
  const href: string = `/insight/${id}`;
  return href as Route;
}
