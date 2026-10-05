import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { messages } from '@/messages';
import { FEATURE, SECOND_FEATURE } from '@/test/atlas';
import { FakeMap, type FakeSource, forgetMaps, loadedMap, setWorkerUrl } from '@/test/maplibre';
import { MAP_MODE_KEY, MapView } from './map-view';

vi.mock('maplibre-gl', () => import('@/test/maplibre'));

afterEach(forgetMaps);

describe('MapView', () => {
  it('builds the map on the tile source of decision 9 and draws the entries as a clustered source', async () => {
    const onMoved = vi.fn();
    render(<MapView features={[FEATURE]} onMoved={onMoved} />);
    const map = await loadedMap();
    expect(map.options.style).toBe('https://tiles.openfreemap.org/styles/liberty');
    // Bundled, the library cannot find its worker beside itself: it is given the served copy.
    expect(setWorkerUrl).toHaveBeenCalledWith('/maplibre/maplibre-gl-worker.mjs');
    expect(map.layers).toEqual(
      expect.arrayContaining(['clusters', 'points', 'cell-fill', 'marker'])
    );
    const data = map.getSource('entries')?.data as { features: { properties: { id: string } }[] };
    expect(data.features.map((feature) => feature.properties.id)).toEqual([FEATURE.id]);
    // The first window is reported once the map is ready, so the page can ask for it.
    expect(onMoved).toHaveBeenCalledWith({ west: 9, south: 35, east: 11, north: 37 }, false, {
      center: [10, 36],
      zoom: 8,
    });
    expect(map.addControl).toHaveBeenCalled();
  });

  it('reports every move, saying whether a hand made it, and selects a point on tap', async () => {
    const onMoved = vi.fn();
    const onSelect = vi.fn();
    const onPick = vi.fn();
    render(<MapView features={[FEATURE]} onMoved={onMoved} onSelect={onSelect} onPick={onPick} />);
    const map = await loadedMap();
    onMoved.mockClear();
    map.emit('moveend', {});
    expect(onMoved).toHaveBeenLastCalledWith(expect.anything(), false, expect.anything());
    map.emit('moveend', { originalEvent: {} });
    expect(onMoved).toHaveBeenLastCalledWith(expect.anything(), true, expect.anything());
    expect(onMoved).toHaveBeenCalledTimes(2);
    map.emit('click:points', { features: [{ properties: { id: FEATURE.id } }] });
    expect(onSelect).toHaveBeenCalledWith(FEATURE.id);
    map.emit('click', { point: { x: 1, y: 1 }, lngLat: { lng: 10.5, lat: 36.5 } });
    expect(onPick).toHaveBeenCalledWith([10.5, 36.5]);
  });

  it('opens a cluster by zooming to it, and follows a new view', async () => {
    const { rerender } = render(<MapView features={[FEATURE, SECOND_FEATURE]} />);
    const map = await loadedMap();
    map.emit('click:clusters', {
      features: [
        { geometry: { type: 'Point', coordinates: [10, 36] }, properties: { cluster_id: 3 } },
      ],
    });
    await vi.waitFor(() => expect(map.easeTo).toHaveBeenCalledWith({ center: [10, 36], zoom: 9 }));
    rerender(
      <MapView features={[FEATURE, SECOND_FEATURE]} view={{ center: [39.8, 21.4], zoom: 10 }} />
    );
    expect(map.flyTo).toHaveBeenCalledWith({ center: [39.8, 21.4], zoom: 10, essential: true });
  });

  it('jumps instead of flying under reduced motion, and marks the selected point', async () => {
    document.documentElement.dataset.motion = 'reduce';
    const { rerender } = render(<MapView features={[FEATURE]} selectedId={null} />);
    const map = await loadedMap();
    rerender(
      <MapView features={[FEATURE]} selectedId={FEATURE.id} view={{ center: [1, 2], zoom: 3 }} />
    );
    expect(map.jumpTo).toHaveBeenCalledWith({ center: [1, 2], zoom: 3 });
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(map.featureState.get(FEATURE.id)).toEqual({ selected: true });
    map.emit('click:clusters', {
      features: [
        { geometry: { type: 'Point', coordinates: [10, 36] }, properties: { cluster_id: 3 } },
      ],
    });
    await vi.waitFor(() => expect(map.jumpTo).toHaveBeenCalledWith({ center: [10, 36], zoom: 9 }));
  });

  it('draws a marker and a cell when asked, and removes the map on unmount', async () => {
    const cell = {
      type: 'Polygon' as const,
      coordinates: [
        [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 0],
        ],
      ],
    };
    const { rerender, unmount } = render(
      <MapView marker={[10, 36]} cell={cell} interactive={false} />
    );
    const map = await loadedMap();
    expect(map.options.interactive).toBe(false);
    expect(map.addControl).not.toHaveBeenCalled();
    expect(
      ((map.getSource('marker') as FakeSource).data as { features: unknown[] }).features
    ).toHaveLength(1);
    expect(
      ((map.getSource('cell') as FakeSource).data as { features: unknown[] }).features
    ).toHaveLength(1);
    rerender(<MapView marker={null} cell={null} interactive={false} />);
    expect(
      ((map.getSource('marker') as FakeSource).data as { features: unknown[] }).features
    ).toHaveLength(0);
    act(() => unmount());
    expect(map.remove).toHaveBeenCalled();
    expect(FakeMap.instances).toHaveLength(1);
  });

  it('ignores a cluster tap without a cluster id and a point tap without an id', async () => {
    const onSelect = vi.fn();
    render(<MapView features={[FEATURE]} onSelect={onSelect} />);
    const map = await loadedMap();
    map.emit('click:clusters', {
      features: [{ geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} }],
    });
    map.emit('click:points', { features: [{ properties: {} }] });
    expect(map.easeTo).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('says so, and does not crash, when the browser has no WebGL2', async () => {
    FakeMap.failWith = new Error('WebGL2 is required');
    const { findByRole } = render(<MapView features={[FEATURE]} />);
    expect((await findByRole('status')).textContent).toBe(messages.atlas.mapUnsupported);
    expect(FakeMap.instances).toHaveLength(0);
  });

  it('leaves the map alone when it finishes loading after the page left', async () => {
    const { unmount } = render(<MapView features={[FEATURE]} />);
    await vi.waitFor(() => expect(FakeMap.instances).toHaveLength(1));
    const map = FakeMap.instances[0] as FakeMap;
    act(() => unmount());
    map.emit('load');
    expect(map.layers).toEqual([]);
    expect(map.remove).toHaveBeenCalled();
  });

  it('does not pick a point when the tap landed on an entry or a cluster', async () => {
    const onPick = vi.fn();
    render(<MapView features={[FEATURE]} onPick={onPick} />);
    const map = await loadedMap();
    map.queryRenderedFeatures.mockReturnValue([{ properties: { id: FEATURE.id } }]);
    map.emit('click', { point: { x: 1, y: 1 }, lngLat: { lng: 10.5, lat: 36.5 } });
    expect(onPick).not.toHaveBeenCalled();
  });

  it('builds no map when the library arrives after the page left', async () => {
    const { unmount } = render(<MapView features={[FEATURE]} />);
    unmount();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(FakeMap.instances).toHaveLength(0);
  });

  it('paints the basemap and the points in the theme colours, and repaints on a theme switch', async () => {
    const root = document.documentElement;
    root.style.setProperty('--map-water', '#123456');
    root.style.setProperty('--point-emerald-halo', '#00aa66');
    render(<MapView features={[FEATURE]} />);
    const map = await loadedMap();

    expect(map.paint.get('water:fill-color')).toBe('#123456');
    expect(map.paint.get('background:background-color')).toBeTruthy();
    // Points of interest stay, from street level only; names are in Arabic first.
    expect(map.layout.get('poi_r1:visibility')).toBe('visible');
    expect(map.zoomRanges.get('poi_r1')).toEqual([15, 24]);
    expect(map.paint.get('clusters:circle-color')).toBe('#00aa66');
    // The app's own layers are never repainted as basemap.
    expect(map.paint.has('points:line-color')).toBe(false);

    root.style.setProperty('--map-water', '#654321');
    root.setAttribute('data-theme', 'dark');
    await vi.waitFor(() => expect(map.paint.get('water:fill-color')).toBe('#654321'));

    root.removeAttribute('data-theme');
    root.style.removeProperty('--map-water');
    root.style.removeProperty('--point-emerald-halo');
  });

  it('has zoom, a compass with tilt, full screen and a metric scale', async () => {
    render(<MapView features={[FEATURE]} />);
    const map = await loadedMap();
    const controls = map.addControl.mock.calls.map(([control, place]) => [
      (control as object).constructor.name,
      place,
    ]);
    expect(controls).toEqual([
      ['NavigationControl', 'top-left'],
      ['FullscreenControl', 'top-left'],
      ['ScaleControl', 'bottom-right'],
    ]);
    const calls = map.addControl.mock.calls as [{ options: unknown }][];
    expect(calls[0]?.[0].options).toEqual({ showCompass: true, visualizePitch: true });
    expect(calls[2]?.[0].options).toEqual({ maxWidth: 110, unit: 'metric' });
  });

  it('switches between the streets and the geographic view, and remembers it on the device', async () => {
    window.localStorage.removeItem(MAP_MODE_KEY);
    const { unmount } = render(<MapView features={[FEATURE]} />);
    const map = await loadedMap();
    const streets = screen.getByRole('button', { name: messages.atlas.mapMode.streets });
    const geographic = screen.getByRole('button', { name: messages.atlas.mapMode.geographic });
    expect(streets).toHaveAttribute('aria-pressed', 'true');
    expect(map.layout.get('road_primary:visibility')).toBe('visible');

    await userEvent.click(geographic);
    expect(geographic).toHaveAttribute('aria-pressed', 'true');
    expect(map.layout.get('road_primary:visibility')).toBe('none');
    expect(window.localStorage.getItem(MAP_MODE_KEY)).toBe('geographic');
    unmount();
    forgetMaps();

    // The next map opens on the view chosen last.
    render(<MapView features={[FEATURE]} />);
    const next = await loadedMap();
    expect(next.layout.get('road_primary:visibility')).toBe('none');
    window.localStorage.removeItem(MAP_MODE_KEY);
  });

  it('keeps the streets when the device will not store the choice, and shows no switch on a still map', async () => {
    const blocked = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const { unmount } = render(<MapView features={[FEATURE]} />);
    await loadedMap();
    await userEvent.click(screen.getByRole('button', { name: messages.atlas.mapMode.geographic }));
    expect(screen.getByRole('button', { name: messages.atlas.mapMode.geographic })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    blocked.mockRestore();
    vi.restoreAllMocks();
    unmount();
    forgetMaps();
    render(<MapView marker={[10, 36]} interactive={false} />);
    await loadedMap();
    expect(screen.queryByRole('button', { name: messages.atlas.mapMode.streets })).toBeNull();
  });

  it('switching before the map is ready only remembers the choice', async () => {
    render(<MapView features={[FEATURE]} />);
    await vi.waitFor(() => expect(FakeMap.instances).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: messages.atlas.mapMode.geographic }));
    expect((FakeMap.instances[0] as FakeMap).setLayoutProperty).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(MAP_MODE_KEY)).toBe('geographic');
    window.localStorage.removeItem(MAP_MODE_KEY);
  });

  it('waits for the map to load before following a theme switch', async () => {
    render(<MapView features={[FEATURE]} />);
    await vi.waitFor(() => expect(FakeMap.instances).toHaveLength(1));
    const map = FakeMap.instances[0] as FakeMap;
    document.documentElement.setAttribute('data-theme', 'dark');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(map.setPaintProperty).not.toHaveBeenCalled();
    document.documentElement.removeAttribute('data-theme');
  });
});
