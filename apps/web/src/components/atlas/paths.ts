import type { Route } from 'next';

export function entryPath(id: string): Route {
  return `/atlas/entries/${id}` as Route;
}

export function placePath(geonameId: number): Route {
  return `/atlas/places/${geonameId}` as Route;
}
