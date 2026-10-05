import { describe, expect, it, vi } from 'vitest';
import {
  AIRPORT_MIN_ZOOM,
  ARABIC_FIRST_NAME,
  BASEMAP_TOKENS,
  basemapColours,
  changesFor,
  POI_MIN_ZOOM,
  themeBasemap,
} from './basemap';

const COLOURS = {
  land: 'land',
  park: 'park',
  water: 'water',
  building: 'building',
  road: 'road',
  roadMajor: 'major',
  boundary: 'boundary',
  label: 'label',
  labelHalo: 'halo',
};
const SHOWN = { kind: 'visible', value: true };
const HIDDEN = { kind: 'visible', value: false };

describe('changesFor, the streets', () => {
  it.each([
    [{ id: 'water', type: 'fill' }, 'fill-color', 'water'],
    [{ id: 'building', type: 'fill' }, 'fill-color', 'building'],
    [{ id: 'building-3d', type: 'fill-extrusion' }, 'fill-extrusion-color', 'building'],
    [{ id: 'park', type: 'fill' }, 'fill-color', 'park'],
    [{ id: 'landcover_wood', type: 'fill' }, 'fill-color', 'park'],
    [{ id: 'landuse_residential', type: 'fill' }, 'fill-color', 'land'],
    [{ id: 'aeroway_fill', type: 'fill' }, 'fill-color', 'land'],
    [{ id: 'landcover_sand', type: 'fill' }, 'fill-opacity', 0.35],
    [{ id: 'landuse_hospital', type: 'fill' }, 'fill-opacity', 0.35],
    [{ id: 'waterway_river', type: 'line' }, 'line-color', 'water'],
    [{ id: 'boundary_2', type: 'line' }, 'line-color', 'boundary'],
    [{ id: 'road_minor_casing', type: 'line' }, 'line-color', 'building'],
    [{ id: 'road_minor', type: 'line' }, 'line-color', 'road'],
    [{ id: 'highway_motorway', type: 'line' }, 'line-color', 'major'],
    [{ id: 'road_primary', type: 'line' }, 'line-color', 'major'],
  ])('shows and colours %o', (layer, property, value) => {
    expect(changesFor(layer, COLOURS)).toEqual([SHOWN, { kind: 'paint', property, value }]);
  });

  it('paints the background, keeps a line it does not know, and leaves other types alone', () => {
    expect(changesFor({ id: 'background', type: 'background' }, COLOURS)).toEqual([
      { kind: 'paint', property: 'background-color', value: 'land' },
    ]);
    expect(changesFor({ id: 'ferry', type: 'line' }, COLOURS)).toEqual([SHOWN]);
    expect(changesFor({ id: 'hills', type: 'hillshade' }, COLOURS)).toEqual([]);
  });

  it('writes place names in Arabic first, but never a road number or an arrow', () => {
    const city = changesFor({ id: 'label_city', type: 'symbol' }, COLOURS);
    expect(city).toEqual([
      SHOWN,
      { kind: 'paint', property: 'text-color', value: 'label' },
      { kind: 'paint', property: 'text-halo-color', value: 'halo' },
      { kind: 'paint', property: 'text-halo-width', value: 1.2 },
      { kind: 'layout', property: 'text-field', value: ARABIC_FIRST_NAME },
    ]);
    expect(ARABIC_FIRST_NAME[1]).toEqual(['get', 'name:ar']);
    for (const id of ['highway-shield-non-us', 'road_one_way_arrow']) {
      expect(changesFor({ id, type: 'symbol' }, COLOURS)).not.toContainEqual(
        expect.objectContaining({ property: 'text-field' })
      );
    }
  });

  it('shows points of interest from street level and airports from the town', () => {
    expect(changesFor({ id: 'poi_r1', type: 'symbol' }, COLOURS)).toContainEqual({
      kind: 'zoom',
      min: POI_MIN_ZOOM,
      max: 24,
    });
    expect(changesFor({ id: 'airport', type: 'symbol' }, COLOURS)).toContainEqual({
      kind: 'zoom',
      min: AIRPORT_MIN_ZOOM,
      max: 24,
    });
  });
});

describe('changesFor, the geographic view', () => {
  it('leaves out roads, buildings and points of interest, and keeps the land, water and names', () => {
    for (const [id, type] of [
      ['road_primary', 'line'],
      ['bridge_street', 'line'],
      ['tunnel_minor', 'line'],
      ['building', 'fill'],
      ['building-3d', 'fill-extrusion'],
      ['poi_r20', 'symbol'],
      ['highway-name-major', 'symbol'],
      ['aeroway_fill', 'fill'],
    ] as const) {
      expect(changesFor({ id, type }, COLOURS, 'geographic')[0]).toEqual(HIDDEN);
    }
    for (const [id, type] of [
      ['water', 'fill'],
      ['landcover_wood', 'fill'],
      ['boundary_2', 'line'],
      ['label_city', 'symbol'],
      ['water_name_point_label', 'symbol'],
    ] as const) {
      expect(changesFor({ id, type }, COLOURS, 'geographic')[0]).toEqual(SHOWN);
    }
  });

  it('brings the shaded relief forward, and puts it back for the streets', () => {
    const [geographic] = changesFor({ id: 'natural_earth', type: 'raster' }, COLOURS, 'geographic');
    const [streets] = changesFor({ id: 'natural_earth', type: 'raster' }, COLOURS);
    expect(geographic).toMatchObject({ kind: 'paint', property: 'raster-opacity' });
    expect(streets).toMatchObject({ kind: 'paint', property: 'raster-opacity' });
    expect(geographic).not.toEqual(streets);
  });
});

describe('themeBasemap', () => {
  function fakeMap(layers: { id: string; type: string }[] | undefined) {
    return {
      getStyle: () => (layers === undefined ? undefined : { layers }),
      setPaintProperty: vi.fn(),
      setLayoutProperty: vi.fn(),
      setLayerZoomRange: vi.fn(),
    };
  }

  it('applies every change, skips the app’s own layers, and survives a refused property', () => {
    const map = fakeMap([
      { id: 'water', type: 'fill' },
      { id: 'poi_r1', type: 'symbol' },
      { id: 'road_primary', type: 'line' },
      { id: 'points', type: 'circle' },
    ]);
    map.setPaintProperty.mockImplementationOnce(() => {
      throw new Error('not a property of this layer');
    });
    themeBasemap(map, COLOURS, new Set(['points']), 'geographic');

    expect(map.setLayoutProperty).toHaveBeenCalledWith('water', 'visibility', 'visible');
    expect(map.setLayoutProperty).toHaveBeenCalledWith('poi_r1', 'visibility', 'none');
    expect(map.setLayoutProperty).toHaveBeenCalledWith('poi_r1', 'text-field', ARABIC_FIRST_NAME);
    expect(map.setLayerZoomRange).toHaveBeenCalledWith('poi_r1', POI_MIN_ZOOM, 24);
    expect(map.setLayoutProperty).toHaveBeenCalledWith('road_primary', 'visibility', 'none');
    expect(map.setPaintProperty).not.toHaveBeenCalledWith(
      'points',
      expect.anything(),
      expect.anything()
    );
  });

  it('does nothing before the style is there', () => {
    const map = fakeMap(undefined);
    themeBasemap(map, COLOURS, new Set());
    expect(map.setPaintProperty).not.toHaveBeenCalled();
  });
});

describe('basemapColours', () => {
  it('reads one token per colour', () => {
    const read = vi.fn((token: string) => `value of ${token}`);
    const colours = basemapColours(read);
    expect(Object.keys(colours)).toEqual(Object.keys(BASEMAP_TOKENS));
    expect(colours.water).toBe('value of --map-water');
  });
});
