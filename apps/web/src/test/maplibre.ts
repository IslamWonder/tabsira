import { vi } from 'vitest';

/*
 * A stand-in for maplibre-gl in unit tests: no canvas, no tiles, no network.
 * It records what the page asks of the map and lets a test fire the map's
 * events. Use it with `vi.mock('maplibre-gl', () => import('@/test/maplibre'))`.
 */

type Handler = (event: unknown) => void;

export class FakeSource {
  data: unknown = null;
  setData = vi.fn((data: unknown) => {
    this.data = data;
  });
  getClusterExpansionZoom = vi.fn(async () => 9);
}

export class FakeMap {
  static instances: FakeMap[] = [];
  /** Set to an error to make the next construction throw, as a browser without WebGL2 does. */
  static failWith: Error | null = null;
  options: Record<string, unknown>;
  sources = new Map<string, FakeSource>();
  layers: string[] = [];
  handlers = new Map<string, Handler[]>();
  featureState = new Map<string, Record<string, unknown>>();
  jumpTo = vi.fn();
  flyTo = vi.fn();
  easeTo = vi.fn();
  remove = vi.fn();
  addControl = vi.fn();
  queryRenderedFeatures = vi.fn((): unknown[] => []);
  bounds = { west: 9, south: 35, east: 11, north: 37 };
  center = { lng: 10, lat: 36 };
  zoom = 8;

  constructor(options: Record<string, unknown>) {
    if (FakeMap.failWith !== null) {
      throw FakeMap.failWith;
    }
    this.options = options;
    FakeMap.instances.push(this);
  }

  on(event: string, layerOrHandler: string | Handler, maybeHandler?: Handler): void {
    const key = typeof layerOrHandler === 'string' ? `${event}:${layerOrHandler}` : event;
    const handler = typeof layerOrHandler === 'string' ? maybeHandler : layerOrHandler;
    if (handler !== undefined) {
      this.handlers.set(key, [...(this.handlers.get(key) ?? []), handler]);
    }
  }

  /** Fire an event the way the map would: `emit('load')`, `emit('click:points', {...})`. */
  emit(key: string, event: unknown = {}): void {
    for (const handler of this.handlers.get(key) ?? []) {
      handler(event);
    }
  }

  addSource(id: string, spec: { data?: unknown } = {}): void {
    const source = new FakeSource();
    source.data = spec.data ?? null;
    this.sources.set(id, source);
  }

  getSource(id: string): FakeSource | undefined {
    return this.sources.get(id);
  }

  /** The basemap's layers, as a style would list them; a test may replace them. */
  styleLayers: { id: string; type: string }[] = [
    { id: 'background', type: 'background' },
    { id: 'water', type: 'fill' },
    { id: 'road_primary', type: 'line' },
    { id: 'poi_r1', type: 'symbol' },
  ];
  paint = new Map<string, unknown>();
  layout = new Map<string, unknown>();
  setPaintProperty = vi.fn((layer: string, property: string, value: unknown) => {
    this.paint.set(`${layer}:${property}`, value);
  });
  setLayoutProperty = vi.fn((layer: string, property: string, value: unknown) => {
    this.layout.set(`${layer}:${property}`, value);
  });
  zoomRanges = new Map<string, [number, number]>();
  setLayerZoomRange = vi.fn((layer: string, min: number, max: number) => {
    this.zoomRanges.set(layer, [min, max]);
  });

  addLayer(layer: { id: string }): void {
    this.layers.push(layer.id);
  }

  getLayer(id: string): { id: string } | undefined {
    return this.layers.includes(id) ? { id } : undefined;
  }

  getStyle(): { layers: { id: string; type: string }[] } {
    return { layers: [...this.styleLayers, ...this.layers.map((id) => ({ id, type: 'circle' }))] };
  }

  setFeatureState(target: { id: string | number }, state: Record<string, unknown>): void {
    this.featureState.set(String(target.id), state);
  }

  getCenter() {
    return this.center;
  }

  getZoom() {
    return this.zoom;
  }

  getBounds() {
    const { west, south, east, north } = this.bounds;
    return {
      getWest: () => west,
      getSouth: () => south,
      getEast: () => east,
      getNorth: () => north,
    };
  }
}

export class NavigationControl {
  constructor(readonly options: unknown = {}) {}
}
export class ScaleControl {
  constructor(readonly options: unknown = {}) {}
}
export class FullscreenControl {}

/** Where the map was told its worker lives. */
export const setWorkerUrl = vi.fn();

/** The newest map the page built, once its load event was fired. */
export async function loadedMap(): Promise<FakeMap> {
  await vi.waitFor(() => {
    if (FakeMap.instances.length === 0) {
      throw new Error('no map yet');
    }
  });
  const map = FakeMap.instances.at(-1) as FakeMap;
  map.emit('load');
  return map;
}

export function forgetMaps(): void {
  FakeMap.instances = [];
  FakeMap.failWith = null;
}

// The name maplibre-gl exports; declared last so nothing above shadows the built-in Map.
export { FakeMap as Map };
