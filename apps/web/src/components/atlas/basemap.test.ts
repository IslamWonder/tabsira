import { describe, expect, it, vi } from 'vitest';
import { BASEMAP_TOKENS, basemapColours, changesFor, themeBasemap } from './basemap';

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

describe('changesFor', () => {
  it.each([
    [{ id: 'background', type: 'background' }, 'background-color', 'land'],
    [{ id: 'water', type: 'fill' }, 'fill-color', 'water'],
    [{ id: 'building', type: 'fill' }, 'fill-color', 'building'],
    [{ id: 'building-3d', type: 'fill-extrusion' }, 'fill-extrusion-color', 'building'],
    [{ id: 'park', type: 'fill' }, 'fill-color', 'park'],
    [{ id: 'landcover_wood', type: 'fill' }, 'fill-color', 'park'],
    [{ id: 'aeroway_fill', type: 'fill' }, 'fill-color', 'land'],
    [{ id: 'waterway_river', type: 'line' }, 'line-color', 'water'],
    [{ id: 'boundary_2', type: 'line' }, 'line-color', 'boundary'],
    [{ id: 'road_minor_casing', type: 'line' }, 'line-color', 'building'],
    [{ id: 'road_minor', type: 'line' }, 'line-color', 'road'],
    [{ id: 'highway_motorway', type: 'line' }, 'line-color', 'major'],
    [{ id: 'road_primary', type: 'line' }, 'line-color', 'major'],
  ])('colours %o', (layer, property, value) => {
    expect(changesFor(layer, COLOURS)).toEqual([{ kind: 'paint', property, value }]);
  });

  it('gives labels the theme text and halo, hides points of interest, leaves the rest', () => {
    expect(changesFor({ id: 'label_city', type: 'symbol' }, COLOURS)).toEqual([
      { kind: 'paint', property: 'text-color', value: 'label' },
      { kind: 'paint', property: 'text-halo-color', value: 'halo' },
      { kind: 'paint', property: 'text-halo-width', value: 1.2 },
    ]);
    expect(changesFor({ id: 'poi_r20', type: 'symbol' }, COLOURS)).toEqual([{ kind: 'hide' }]);
    expect(changesFor({ id: 'airport', type: 'symbol' }, COLOURS)).toEqual([{ kind: 'hide' }]);
    expect(changesFor({ id: 'hillshade', type: 'hillshade' }, COLOURS)).toEqual([]);
    expect(changesFor({ id: 'ferry', type: 'line' }, COLOURS)).toEqual([]);
  });
});

describe('themeBasemap', () => {
  it('repaints every basemap layer, skips the app layers and survives a refused property', () => {
    const map = {
      getStyle: () => ({
        layers: [
          { id: 'water', type: 'fill' },
          { id: 'points', type: 'circle' },
          { id: 'poi', type: 'symbol' },
          { id: 'road_minor', type: 'line' },
        ],
      }),
      setPaintProperty: vi.fn((layer: string) => {
        if (layer === 'road_minor') {
          throw new Error('no such property');
        }
      }),
      setLayoutProperty: vi.fn(),
    };

    themeBasemap(map, COLOURS, new Set(['points']));

    expect(map.setPaintProperty).toHaveBeenCalledWith('water', 'fill-color', 'water');
    expect(map.setPaintProperty).not.toHaveBeenCalledWith(
      'points',
      expect.anything(),
      expect.anything()
    );
    expect(map.setLayoutProperty).toHaveBeenCalledWith('poi', 'visibility', 'none');
  });

  it('does nothing on a map without a style yet', () => {
    const map = {
      getStyle: () => undefined,
      setPaintProperty: vi.fn(),
      setLayoutProperty: vi.fn(),
    };
    themeBasemap(map, COLOURS, new Set());
    expect(map.setPaintProperty).not.toHaveBeenCalled();
  });

  it('reads every colour from its token', () => {
    const colours = basemapColours((name) => `value of ${name}`);
    expect(colours.water).toBe(`value of ${BASEMAP_TOKENS.water}`);
    expect(Object.keys(colours)).toHaveLength(9);
  });
});
