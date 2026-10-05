import type { Route } from 'next';
import { messages } from '@/messages';
import type { Place, PlaceInsight, Reveal, World, WorldTheme } from '@/world/api';

/*
 * What the world screen shows, derived from the one answer of GET /world
 * (decision 59): the landmarks of the regions something was learned in, and
 * every learned insight for «بصائري». Nothing here knows a region still under
 * the clouds: only what was learned is drawn, named or listed.
 */

/** The colour of a landmark's ring and drawing, per theme: a design symbol, never a ruling. */
export const THEME_COLORS: Readonly<Record<WorldTheme, string>> = {
  water: '#83e1d5',
  planting: '#b3d178',
  knowledge: '#f3d382',
  patience: '#dacdb8',
  kinship: '#f2c4b3',
  justice: '#e3cf9a',
};

/** A region's landmark: its first reveal, where its marker stands, with the place it opens. */
export interface Landmark {
  reveal: Reveal;
  place: Place | null;
  name: string;
}

/** A learned insight, with its place and the reveal that shows where it lies. */
export interface Learned {
  insight: PlaceInsight;
  place: Place;
  /** Its concept's reveal, or its region's landmark when the region had no room left. */
  spot: Reveal | null;
}

function regionName(world: World, regionId: string): string {
  return world.regions.find((region) => region.id === regionId)?.name ?? regionId;
}

export function landmarks(world: World): Landmark[] {
  const places = new Map(world.places.map((place) => [place.id, place]));
  return world.reveals
    .filter((reveal) => reveal.landmark)
    .map((reveal) => {
      const place = places.get(reveal.place_id) ?? null;
      return { reveal, place, name: place?.name ?? regionName(world, reveal.region_id) };
    });
}

/** The landmark reveal of a place, if its region has one. */
export function landmarkOf(world: World, placeId: string): Reveal | null {
  return world.reveals.find((reveal) => reveal.landmark && reveal.place_id === placeId) ?? null;
}

/** Every learned insight, the most recent first. */
export function learned(world: World): Learned[] {
  const reveals = new Map(world.reveals.map((reveal) => [reveal.id, reveal]));
  const items = world.places.flatMap((place) =>
    place.insights.map((insight) => ({
      insight,
      place,
      spot:
        (insight.reveal_id === null ? undefined : reveals.get(insight.reveal_id)) ??
        landmarkOf(world, place.id),
    }))
  );
  return items.sort((a, b) => b.insight.completed_at.localeCompare(a.insight.completed_at));
}

/** The reveals the world has not played yet, in the order they were learned. */
export function pendingReveals(world: World): Reveal[] {
  return world.reveals.filter((reveal) => !reveal.shown);
}

/** The name a reveal opens: its region's landmark, for the announcement after a save. */
export function revealName(world: World, reveal: Reveal): string {
  return (
    world.places.find((place) => place.id === reveal.place_id)?.name ??
    regionName(world, reveal.region_id)
  );
}

/**
 * What a screen reader hears once reveals have played (the kit's «حُفظت بصيرتك، وانكشف …»):
 * the landmarks that appeared, or the region that widened; nothing for reveals it does not know.
 */
export function announcement(world: World, ids: readonly string[]): string {
  const reveals = world.reveals.filter((reveal) => ids.includes(reveal.id));
  const names = reveals
    .filter((reveal) => reveal.landmark)
    .map((reveal) => revealName(world, reveal));
  if (names.length > 0) {
    return messages.world.revealed(names);
  }
  const first = reveals[0];
  return first === undefined ? '' : messages.world.widened(revealName(world, first));
}

/**
 * The route of an insight's own screen, built by the scan and insight flow. The
 * typed-routes list only knows it once that route exists, hence the cast.
 */
export function insightHref(id: string): Route {
  const href: string = `/insight/${id}`;
  return href as Route;
}
