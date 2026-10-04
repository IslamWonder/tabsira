/*
 * The OpenFreeMap basemap in the app's own colours. The style's layers keep
 * their geometry and their labels; only their paint changes, from the
 * `--map-*` tokens of theme/tokens.css, so the map follows the light and dark
 * themes like every other surface. Points of interest are hidden: the atlas
 * shows insights, and a shop icon beside a point would compete with it.
 */

export interface BasemapColours {
  land: string;
  park: string;
  water: string;
  building: string;
  road: string;
  roadMajor: string;
  boundary: string;
  label: string;
  labelHalo: string;
}

export const BASEMAP_TOKENS: Record<keyof BasemapColours, string> = {
  land: '--map-land',
  park: '--map-park',
  water: '--map-water',
  building: '--map-building',
  road: '--map-road',
  roadMajor: '--map-road-major',
  boundary: '--map-boundary',
  label: '--map-label',
  labelHalo: '--map-label-halo',
};

/** One style layer as the map lists it: its id and its type are all the rules need. */
export interface StyleLayer {
  id: string;
  type: string;
}

export type LayerChange =
  | { kind: 'paint'; property: string; value: string | number }
  | { kind: 'hide' };

const MAJOR_ROAD = /motorway|trunk|primary|major|highway/;

/** Return what to change on one layer of the basemap; empty for a layer left as it is. */
export function changesFor(layer: StyleLayer, colours: BasemapColours): LayerChange[] {
  const id = layer.id;
  if (/^poi|aeroway.*label|^airport/.test(id)) {
    return [{ kind: 'hide' }];
  }
  switch (layer.type) {
    case 'background':
      return [{ kind: 'paint', property: 'background-color', value: colours.land }];
    case 'fill':
    case 'fill-extrusion': {
      const property = layer.type === 'fill' ? 'fill-color' : 'fill-extrusion-color';
      if (/water/.test(id)) {
        return [{ kind: 'paint', property, value: colours.water }];
      }
      if (/building/.test(id)) {
        return [{ kind: 'paint', property, value: colours.building }];
      }
      if (/park|grass|wood|forest|landcover|landuse|cemetery|pitch|farmland|scrub/.test(id)) {
        return [{ kind: 'paint', property, value: colours.park }];
      }
      return [{ kind: 'paint', property, value: colours.land }];
    }
    case 'line':
      if (/water|river|stream|canal/.test(id)) {
        return [{ kind: 'paint', property: 'line-color', value: colours.water }];
      }
      if (/boundary|admin/.test(id)) {
        return [{ kind: 'paint', property: 'line-color', value: colours.boundary }];
      }
      if (/casing|outline/.test(id)) {
        return [{ kind: 'paint', property: 'line-color', value: colours.building }];
      }
      if (/road|highway|street|path|track|bridge|tunnel|rail|transit|aeroway/.test(id)) {
        return [
          {
            kind: 'paint',
            property: 'line-color',
            value: MAJOR_ROAD.test(id) ? colours.roadMajor : colours.road,
          },
        ];
      }
      return [];
    case 'symbol':
      return [
        { kind: 'paint', property: 'text-color', value: colours.label },
        { kind: 'paint', property: 'text-halo-color', value: colours.labelHalo },
        { kind: 'paint', property: 'text-halo-width', value: 1.2 },
      ];
    default:
      return [];
  }
}

/** The part of a MapLibre map the basemap needs: easy to fake in tests. */
export interface ThemableMap {
  getStyle(): { layers?: StyleLayer[] } | undefined;
  setPaintProperty(layer: string, property: string, value: unknown): void;
  setLayoutProperty(layer: string, property: string, value: unknown): void;
}

/** Repaint every basemap layer from the colours; the app's own layers are left out. */
export function themeBasemap(
  map: ThemableMap,
  colours: BasemapColours,
  ownLayers: ReadonlySet<string>
): void {
  for (const layer of map.getStyle()?.layers ?? []) {
    if (ownLayers.has(layer.id)) {
      continue;
    }
    for (const change of changesFor(layer, colours)) {
      try {
        if (change.kind === 'hide') {
          map.setLayoutProperty(layer.id, 'visibility', 'none');
        } else {
          map.setPaintProperty(layer.id, change.property, change.value);
        }
      } catch {
        // A property the layer does not take (a style update upstream): its own colour stays.
      }
    }
  }
}

/** Read the basemap colours of the theme in force from the document. */
export function basemapColours(read: (token: string) => string): BasemapColours {
  const entries = Object.entries(BASEMAP_TOKENS).map(([key, token]) => [key, read(token)]);
  return Object.fromEntries(entries) as unknown as BasemapColours;
}
