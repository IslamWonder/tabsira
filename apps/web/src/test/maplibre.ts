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

  constructor(options: Record<string, unknown>) {
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

  addLayer(layer: { id: string }): void {
    this.layers.push(layer.id);
  }

  setFeatureState(target: { id: string | number }, state: Record<string, unknown>): void {
    this.featureState.set(String(target.id), state);
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

export class NavigationControl {}

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
}

// The name maplibre-gl exports; declared last so nothing above shadows the built-in Map.
export { FakeMap as Map };
