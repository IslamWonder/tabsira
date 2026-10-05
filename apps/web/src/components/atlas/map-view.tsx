'use client';

import Link from 'next/link';
import 'maplibre-gl/dist/maplibre-gl.css';

import type { FeatureCollection, Polygon } from 'geojson';
import type {
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
  LngLatLike,
  Map as MapLibreMap,
} from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import type { AtlasFeature, Window } from '@/atlas/types';
import { DEFAULT_VIEW, lngLatOf, MAP_STYLE_URL } from '@/atlas/types';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { basemapColours, type ThemableMap, themeBasemap } from './basemap';

const A = messages.atlas;

export interface MapViewProps {
  /** The published entries to draw; clustered by the map itself. */
  features?: readonly AtlasFeature[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** The window after every move, with the centre and zoom; `byHand` says a person dragged or zoomed, not the page. */
  onMoved?: (
    window: Window,
    byHand: boolean,
    view: { center: [number, number]; zoom: number }
  ) => void;
  /** Where to look; a change flies there (or jumps, under reduced motion). */
  view?: { center: [number, number]; zoom: number } | null;
  /** A single point to mark: a chosen capture point, or an entry's public point. */
  marker?: [number, number] | null;
  /** A cell to shade: what the atlas will show for a chosen point. */
  cell?: Polygon | null;
  /** A tap on the map, for choosing a point. */
  onPick?: (lngLat: [number, number]) => void;
  interactive?: boolean;
  className?: string;
}

const SOURCE = 'entries';
const CELL_SOURCE = 'cell';
const MARKER_SOURCE = 'marker';

function windowOf(map: MapLibreMap): Window {
  const bounds = map.getBounds();
  return {
    west: bounds.getWest(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    north: bounds.getNorth(),
  };
}

function viewOf(map: MapLibreMap): { center: [number, number]; zoom: number } {
  const center = map.getCenter();
  return { center: [center.lng, center.lat], zoom: map.getZoom() };
}

function reducedMotion(): boolean {
  return (
    document.documentElement.dataset.motion === 'reduce' ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

function collection(features: readonly AtlasFeature[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((feature) => ({
      type: 'Feature',
      id: Number(feature.id.slice(-9)),
      geometry: { type: 'Point', coordinates: lngLatOf(feature.geometry) },
      properties: { id: feature.id, title: feature.properties.title },
    })),
  };
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#3fd69a';
}

/** The app's own layers: the basemap theming leaves them to `paintOwnLayers`. */
const OWN_LAYERS: ReadonlySet<string> = new Set([
  'cluster-halo',
  'clusters',
  'cluster-count',
  'point-halo',
  'points',
  'cell-fill',
  'cell-line',
  'marker-halo',
  'marker',
]);

const SELECTED: ExpressionSpecification = ['boolean', ['feature-state', 'selected'], false];

/**
 * Paint the insight points the way the scene photo draws its points (a soft
 * halo, a core, a thin ring), emerald, and gold for the one selected; a
 * cluster is an emerald disc in a gold ring. Every colour is a theme token.
 */
function paintOwnLayers(map: MapLibreMap): void {
  // The same narrow surface the basemap uses: a layer id, a paint property, a value.
  // Every layer named here was added before the first paint.
  const paint = map as unknown as ThemableMap;
  const set = (layer: string, property: string, value: unknown) =>
    paint.setPaintProperty(layer, property, value);
  const emeraldHalo = token('--point-emerald-halo');
  const emeraldCore = token('--point-emerald-core');
  const goldHalo = token('--point-gold-halo');
  const goldCore = token('--point-gold-core');
  const ring = token('--point-ring');
  set('cluster-halo', 'circle-color', emeraldHalo);
  set('clusters', 'circle-color', emeraldHalo);
  set('clusters', 'circle-stroke-color', goldHalo);
  set('point-halo', 'circle-color', ['case', SELECTED, goldHalo, emeraldHalo]);
  set('points', 'circle-color', ['case', SELECTED, goldCore, emeraldCore]);
  set('points', 'circle-stroke-color', ring);
  set('cell-fill', 'fill-color', goldHalo);
  set('cell-line', 'line-color', goldHalo);
  set('marker-halo', 'circle-color', goldHalo);
  set('marker', 'circle-color', goldCore);
  set('marker', 'circle-stroke-color', ring);
}

/** Repaint the basemap and the app's layers from the theme in force. */
function applyTheme(map: MapLibreMap): void {
  themeBasemap(map as unknown as ThemableMap, basemapColours(token), OWN_LAYERS);
  paintOwnLayers(map);
}

/**
 * The real map (decision 9: MapLibre with OpenFreeMap tiles, the one third-party
 * request besides consented analytics). Clusters at far zooms, single points
 * near; a point stands for an insight, never for a person. The map itself is
 * decorative to assistive technology: every result is also a list beside it,
 * and a tap on a point selects the same item the list does. Motion only on
 * events, and none under reduced motion.
 */
export function MapView({
  features = [],
  selectedId = null,
  onSelect,
  onMoved,
  view = null,
  marker = null,
  cell = null,
  onPick,
  interactive = true,
  className,
}: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const [unsupported, setUnsupported] = useState(false);
  const map = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  const handlers = useRef({ onSelect, onMoved, onPick });
  handlers.current = { onSelect, onMoved, onPick };
  const latest = useRef({ features, marker, cell, selectedId });
  latest.current = { features, marker, cell, selectedId };

  // The map is built once, on display; later changes reach it through the effects below.
  // biome-ignore lint/correctness/useExhaustiveDependencies: built once; `view` and `interactive` are read at that moment only.
  useEffect(() => {
    let cancelled = false;
    void import('maplibre-gl').then(({ Map: MapLibre, NavigationControl }) => {
      if (cancelled || container.current === null) {
        return;
      }
      let instance: MapLibreMap;
      try {
        instance = new MapLibre({
          container: container.current,
          style: MAP_STYLE_URL,
          center: view?.center ?? DEFAULT_VIEW.center,
          zoom: view?.zoom ?? DEFAULT_VIEW.zoom,
          interactive,
          attributionControl: false,
          // A pointer that moves is a scroll, not a zoom, until the map is touched (Jakob's law).
          cooperativeGestures: interactive,
        });
      } catch {
        // No WebGL2 (old device, blocked GPU, headless browser): the list beside the map still works.
        setUnsupported(true);
        return;
      }
      map.current = instance;
      if (interactive) {
        instance.addControl(new NavigationControl({ showCompass: false }), 'top-left');
      }
      instance.on('load', () => {
        if (cancelled) {
          return;
        }
        instance.addSource(SOURCE, {
          type: 'geojson',
          data: collection(latest.current.features),
          cluster: true,
          clusterRadius: 48,
          clusterMaxZoom: 15,
          promoteId: 'id',
        });
        const clustered: FilterSpecification = ['has', 'point_count'];
        const single: FilterSpecification = ['!', ['has', 'point_count']];
        const clusterSize: ExpressionSpecification = [
          'step',
          ['get', 'point_count'],
          15,
          10,
          19,
          50,
          24,
        ];
        instance.addLayer({
          id: 'cluster-halo',
          type: 'circle',
          source: SOURCE,
          filter: clustered,
          paint: {
            'circle-radius': ['+', clusterSize, 9],
            'circle-blur': 0.9,
            'circle-opacity': 0.45,
          },
        });
        instance.addLayer({
          id: 'clusters',
          type: 'circle',
          source: SOURCE,
          filter: clustered,
          paint: {
            'circle-radius': clusterSize,
            'circle-opacity': 0.95,
            'circle-stroke-width': 2,
          },
        });
        instance.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: SOURCE,
          filter: clustered,
          layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 13 },
          paint: { 'text-color': '#04130d' },
        });
        instance.addLayer({
          id: 'point-halo',
          type: 'circle',
          source: SOURCE,
          filter: single,
          paint: {
            'circle-radius': ['case', SELECTED, 20, 14],
            'circle-blur': 0.85,
            'circle-opacity': 0.6,
          },
        });
        instance.addLayer({
          id: 'points',
          type: 'circle',
          source: SOURCE,
          filter: single,
          paint: {
            'circle-radius': ['case', SELECTED, 8, 6],
            'circle-stroke-width': 2,
          },
        });
        instance.addSource(CELL_SOURCE, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        instance.addLayer({
          id: 'cell-fill',
          type: 'fill',
          source: CELL_SOURCE,
          paint: { 'fill-opacity': 0.18 },
        });
        instance.addLayer({
          id: 'cell-line',
          type: 'line',
          source: CELL_SOURCE,
          paint: { 'line-width': 1.5 },
        });
        instance.addSource(MARKER_SOURCE, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        instance.addLayer({
          id: 'marker-halo',
          type: 'circle',
          source: MARKER_SOURCE,
          paint: { 'circle-radius': 20, 'circle-blur': 0.85, 'circle-opacity': 0.6 },
        });
        instance.addLayer({
          id: 'marker',
          type: 'circle',
          source: MARKER_SOURCE,
          paint: { 'circle-radius': 8, 'circle-stroke-width': 2 },
        });
        applyTheme(instance);
        ready.current = true;
        applyMarker(instance, latest.current.marker, latest.current.cell);
        applySelection(instance, latest.current.features, latest.current.selectedId);

        instance.on('click', 'points', (event) => {
          const id = event.features?.[0]?.properties?.id;
          if (typeof id === 'string') {
            handlers.current.onSelect?.(id);
          }
        });
        instance.on('click', 'clusters', (event) => {
          const feature = event.features?.[0];
          const clusterId = feature?.properties?.cluster_id;
          const source = instance.getSource<GeoJSONSource>(SOURCE);
          if (feature?.geometry.type !== 'Point' || typeof clusterId !== 'number' || !source) {
            return;
          }
          const geometry = feature.geometry;
          void source.getClusterExpansionZoom(clusterId).then((zoom) => {
            const center = geometry.coordinates as [number, number];
            if (reducedMotion()) {
              instance.jumpTo({ center, zoom });
            } else {
              instance.easeTo({ center, zoom });
            }
          });
        });
        instance.on('click', (event) => {
          const hits = instance.queryRenderedFeatures(event.point, {
            layers: ['points', 'clusters'],
          });
          if (hits.length === 0) {
            handlers.current.onPick?.([event.lngLat.lng, event.lngLat.lat]);
          }
        });
        instance.on('moveend', (event: { originalEvent?: unknown }) => {
          handlers.current.onMoved?.(
            windowOf(instance),
            event.originalEvent !== undefined,
            viewOf(instance)
          );
        });
        handlers.current.onMoved?.(windowOf(instance), false, viewOf(instance));
      });
    });
    return () => {
      cancelled = true;
      ready.current = false;
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // The map follows the app's theme: a switch in the settings or in the system repaints it.
  useEffect(() => {
    const repaint = () => {
      const instance = map.current;
      if (instance !== null && ready.current) {
        applyTheme(instance);
      }
    };
    const observer = new MutationObserver(repaint);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    const scheme = window.matchMedia('(prefers-color-scheme: dark)');
    scheme.addEventListener('change', repaint);
    return () => {
      observer.disconnect();
      scheme.removeEventListener('change', repaint);
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (instance === null || !ready.current) {
      return;
    }
    const source = instance.getSource<GeoJSONSource>(SOURCE);
    source?.setData(collection(features));
    applySelection(instance, features, selectedId);
  }, [features, selectedId]);

  useEffect(() => {
    const instance = map.current;
    if (instance !== null && ready.current) {
      applyMarker(instance, marker, cell);
    }
  }, [marker, cell]);

  useEffect(() => {
    const instance = map.current;
    if (instance === null || view === null) {
      return;
    }
    if (reducedMotion()) {
      instance.jumpTo({ center: view.center as LngLatLike, zoom: view.zoom });
    } else {
      instance.flyTo({ center: view.center as LngLatLike, zoom: view.zoom, essential: true });
    }
  }, [view]);

  return (
    <div className={cx('relative h-full w-full', className)}>
      <div ref={container} aria-hidden="true" className="h-full w-full" data-testid="map-canvas" />
      {unsupported ? (
        <p
          role="status"
          className="absolute inset-0 m-0 flex items-center justify-center bg-[var(--surface-glass)] p-4 text-center text-fg-muted"
        >
          {A.mapUnsupported}
        </p>
      ) : null}
      <nav
        aria-label={A.attribution.label}
        className="absolute bottom-1 start-1 flex flex-wrap gap-x-2 rounded bg-[var(--surface-glass)] px-2 py-0.5 text-[0.6875rem] text-fg-muted"
      >
        {A.attribution.links.map(([name, href]) => (
          <a
            key={href}
            href={href}
            dir="ltr"
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            {name}
          </a>
        ))}
        <Link href="/sources" className="underline">
          {A.attribution.more}
        </Link>
      </nav>
    </div>
  );
}

function applySelection(
  instance: MapLibreMap,
  features: readonly AtlasFeature[],
  selectedId: string | null
): void {
  for (const feature of features) {
    instance.setFeatureState(
      { source: SOURCE, id: feature.id },
      { selected: feature.id === selectedId }
    );
  }
}

function applyMarker(
  instance: MapLibreMap,
  marker: [number, number] | null,
  cell: Polygon | null
): void {
  const markerSource = instance.getSource<GeoJSONSource>(MARKER_SOURCE);
  markerSource?.setData({
    type: 'FeatureCollection',
    features:
      marker === null
        ? []
        : [{ type: 'Feature', geometry: { type: 'Point', coordinates: marker }, properties: {} }],
  });
  const cellSource = instance.getSource<GeoJSONSource>(CELL_SOURCE);
  cellSource?.setData({
    type: 'FeatureCollection',
    features: cell === null ? [] : [{ type: 'Feature', geometry: cell, properties: {} }],
  });
}
