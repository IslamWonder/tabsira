import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FEATURE } from '@/test/atlas';
import { forgetMaps, loadedMap } from '@/test/maplibre';
import { PIN_IMAGE, PIN_PIXEL_RATIO } from './map-pin';
import { MapView } from './map-view';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));
// A browser whose canvas draws: the pin exists (map-pin.test.tsx tests the drawing itself).
const PIN = { width: 96, height: 120, data: new Uint8ClampedArray(96 * 120 * 4) };
vi.mock('./map-pin', async (actual) => ({
  ...(await actual<typeof import('./map-pin')>()),
  drawPin: () => PIN,
}));

afterEach(forgetMaps);

const spec = (map: Awaited<ReturnType<typeof loadedMap>>, id: string) =>
  map.specs.find((layer) => layer.id === id) as {
    type: string;
    layout?: Record<string, unknown>;
    paint?: Record<string, unknown>;
  };

describe('MapView with the pin', () => {
  it('draws every place as the pin standing on its tip, and the chosen one larger with a glow', async () => {
    render(<MapView features={[FEATURE]} />);
    const map = await loadedMap();
    expect(map.addImage).toHaveBeenCalledWith(PIN_IMAGE, PIN, { pixelRatio: PIN_PIXEL_RATIO });

    const points = spec(map, 'points');
    const chosen = spec(map, 'point-selected');
    expect(points.type).toBe('symbol');
    expect(points.layout).toMatchObject({
      'icon-image': PIN_IMAGE,
      'icon-anchor': 'bottom',
      'icon-allow-overlap': true,
    });
    expect(chosen.layout?.['icon-size'] as number).toBeGreaterThan(
      points.layout?.['icon-size'] as number
    );
    // One pin shows at a time: the small one, or the large one when chosen.
    expect(points.paint?.['icon-opacity']).toEqual([
      'case',
      ['boolean', ['feature-state', 'selected'], false],
      0,
      1,
    ]);
    // The glow is the chosen place's alone.
    expect(spec(map, 'point-halo').paint?.['circle-opacity']).toEqual([
      'case',
      ['boolean', ['feature-state', 'selected'], false],
      0.6,
      0,
    ]);
    // The pin keeps its own colours: no circle paint lands on it.
    expect(map.paint.has('points:circle-color')).toBe(false);
    expect(map.paint.has('marker:circle-color')).toBe(false);
    expect(spec(map, 'marker').type).toBe('symbol');
  });

  it('selects a place from either pin, and picks a point only off the pins', async () => {
    const onSelect = vi.fn();
    const onPick = vi.fn();
    render(<MapView features={[FEATURE]} onSelect={onSelect} onPick={onPick} />);
    const map = await loadedMap();
    map.emit('click:point-selected', { features: [{ properties: { id: FEATURE.id } }] });
    map.emit('click:points', { features: [{ properties: { id: FEATURE.id } }] });
    expect(onSelect).toHaveBeenCalledTimes(2);

    map.emit('click', { point: { x: 1, y: 1 }, lngLat: { lng: 10.5, lat: 36.5 } });
    expect(map.queryRenderedFeatures).toHaveBeenCalledWith(
      { x: 1, y: 1 },
      { layers: ['points', 'point-selected', 'clusters'] }
    );
    expect(onPick).toHaveBeenCalledWith([10.5, 36.5]);
  });
});
