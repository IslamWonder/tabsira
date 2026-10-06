/*
 * The OpenFreeMap basemap in the app's own colours. The style's layers keep
 * their geometry and their labels; only their paint changes, from the
 * `--map-*` tokens of theme/tokens.css, so the map follows the light and dark
 * themes like every other surface. Place names are written in Arabic first.
 * Points of interest appear from street level only, below the insights.
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

/**
 * How the basemap is drawn: the streets view shows the streets, buildings and places of
 * the town; the geographic view shows the land itself, its relief, water and vegetation,
 * borders and place names, without the roads. Both come from the same tiles.
 */
export type MapMode = 'streets' | 'geographic';
export const MAP_MODES: readonly MapMode[] = ['streets', 'geographic'];

export type LayerChange =
  | { kind: 'paint'; property: string; value: unknown }
  | { kind: 'layout'; property: string; value: unknown }
  | { kind: 'visible'; value: boolean }
  | { kind: 'zoom'; min: number; max: number };

const MAJOR_ROAD = /motorway|trunk|primary|major|highway/;
/** What the geographic view leaves out: the built world. */
const BUILT = /^(road_|tunnel_|bridge_|building|highway-|road_shield|aeroway_|airport|poi_)/;
/** Labels that carry a name (not a road number or a one-way arrow). */
const NAMED = /^(label_|water_name|waterway_line_label|highway-name|poi_|airport)/;
/** Areas whose own colour tells what they are; softened so both themes stay calm. */
const KEPT_COLOUR = /sand|ice|wetland|school|hospital|cemetery|pitch|track/;
/** Shops, places of worship and stations: from street level only, below the insights. */
export const POI_MIN_ZOOM = 15;
export const AIRPORT_MIN_ZOOM = 11;

/**
 * The Arabic name first (OpenStreetMap's `name:ar`), then the local one, then
 * any: the app reads in Arabic, so the Arabic name of Tunis before its Latin one, on one line.
 */
export const ARABIC_FIRST_NAME = [
  'coalesce',
  ['get', 'name:ar'],
  ['get', 'name:nonlatin'],
  ['get', 'name'],
  ['get', 'name_en'],
  ['get', 'name:latin'],
];

/** The shaded relief of Natural Earth: faint under the streets, plain in the geographic view. */
const RELIEF_OPACITY: Record<MapMode, unknown> = {
  streets: ['interpolate', ['exponential', 1.5], ['zoom'], 0, 0.6, 6, 0.1],
  geographic: ['interpolate', ['linear'], ['zoom'], 0, 0.9, 6, 0.6, 10, 0.3],
};

function fillChanges(id: string, property: string, colours: BasemapColours): LayerChange[] {
  if (/water/.test(id)) {
    return [{ kind: 'paint', property, value: colours.water }];
  }
  if (/building/.test(id)) {
    return [{ kind: 'paint', property, value: colours.building }];
  }
  if (/park|grass|wood|forest|landcover|farmland|scrub/.test(id) && !KEPT_COLOUR.test(id)) {
    return [{ kind: 'paint', property, value: colours.park }];
  }
  if (KEPT_COLOUR.test(id)) {
    return [{ kind: 'paint', property: 'fill-opacity', value: 0.35 }];
  }
  return [{ kind: 'paint', property, value: colours.land }];
}

function lineChanges(id: string, colours: BasemapColours): LayerChange[] {
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
}

function symbolChanges(id: string, colours: BasemapColours): LayerChange[] {
  const changes: LayerChange[] = [
    { kind: 'paint', property: 'text-color', value: colours.label },
    { kind: 'paint', property: 'text-halo-color', value: colours.labelHalo },
    { kind: 'paint', property: 'text-halo-width', value: 1.2 },
  ];
  if (NAMED.test(id)) {
    changes.push({ kind: 'layout', property: 'text-field', value: ARABIC_FIRST_NAME });
  }
  if (id.startsWith('poi_')) {
    changes.push({ kind: 'zoom', min: POI_MIN_ZOOM, max: 24 });
  } else if (id.startsWith('airport')) {
    changes.push({ kind: 'zoom', min: AIRPORT_MIN_ZOOM, max: 24 });
  }
  return changes;
}

/** Return what to change on one layer of the basemap; empty for a layer left as it is. */
export function changesFor(
  layer: StyleLayer,
  colours: BasemapColours,
  mode: MapMode = 'streets'
): LayerChange[] {
  const id = layer.id;
  const shown: LayerChange = { kind: 'visible', value: mode === 'streets' || !BUILT.test(id) };
  switch (layer.type) {
    case 'background':
      return [{ kind: 'paint', property: 'background-color', value: colours.land }];
    case 'raster':
      return [{ kind: 'paint', property: 'raster-opacity', value: RELIEF_OPACITY[mode] }];
    case 'fill':
    case 'fill-extrusion': {
      const property = layer.type === 'fill' ? 'fill-color' : 'fill-extrusion-color';
      return [shown, ...fillChanges(id, property, colours)];
    }
    case 'line':
      return [shown, ...lineChanges(id, colours)];
    case 'symbol':
      return [shown, ...symbolChanges(id, colours)];
    default:
      return [];
  }
}

/** The part of a MapLibre map the basemap needs: easy to fake in tests. */
export interface ThemableMap {
  getStyle(): { layers?: StyleLayer[] } | undefined;
  setPaintProperty(layer: string, property: string, value: unknown): void;
  setLayoutProperty(layer: string, property: string, value: unknown): void;
  setLayerZoomRange(layer: string, min: number, max: number): void;
}

function apply(map: ThemableMap, id: string, change: LayerChange): void {
  switch (change.kind) {
    case 'paint':
      map.setPaintProperty(id, change.property, change.value);
      return;
    case 'layout':
      map.setLayoutProperty(id, change.property, change.value);
      return;
    case 'visible':
      map.setLayoutProperty(id, 'visibility', change.value ? 'visible' : 'none');
      return;
    case 'zoom':
      map.setLayerZoomRange(id, change.min, change.max);
  }
}

/** Repaint every basemap layer for the colours and the mode; the app's own layers are left out. */
export function themeBasemap(
  map: ThemableMap,
  colours: BasemapColours,
  ownLayers: ReadonlySet<string>,
  mode: MapMode = 'streets'
): void {
  for (const layer of map.getStyle()?.layers ?? []) {
    if (ownLayers.has(layer.id)) {
      continue;
    }
    for (const change of changesFor(layer, colours, mode)) {
      try {
        apply(map, layer.id, change);
      } catch {
        // A property the layer does not take (a style update upstream): its own value stays.
      }
    }
  }
}

/** Read the basemap colours of the theme in force from the document. */
export function basemapColours(read: (token: string) => string): BasemapColours {
  const entries = Object.entries(BASEMAP_TOKENS).map(([key, token]) => [key, read(token)]);
  return Object.fromEntries(entries) as unknown as BasemapColours;
}
