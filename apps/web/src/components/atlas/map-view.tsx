'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import type { FeatureCollection, Polygon } from 'geojson';
import type { GeoJSONSource, LngLatLike, Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import type { AtlasFeature, Window } from '@/atlas/types';
import { DEFAULT_VIEW, lngLatOf, MAP_STYLE_URL } from '@/atlas/types';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

const A = messages.atlas;

export interface MapViewProps {
  /** The published entries to draw; clustered by the map itself. */
  features?: readonly AtlasFeature[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** The window after every move; `byHand` says a person dragged or zoomed, not the page. */
  onMoved?: (window: Window, byHand: boolean) => void;
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
      const instance = new MapLibre({
        container: container.current,
        style: MAP_STYLE_URL,
        center: view?.center ?? DEFAULT_VIEW.center,
        zoom: view?.zoom ?? DEFAULT_VIEW.zoom,
        interactive,
        attributionControl: false,
        // A pointer that moves is a scroll, not a zoom, until the map is touched (Jakob's law).
        cooperativeGestures: interactive,
      });
      map.current = instance;
      if (interactive) {
        instance.addControl(new NavigationControl({ showCompass: false }), 'top-left');
      }
      instance.on('load', () => {
        if (cancelled) {
          return;
        }
        const emerald = token('--glow-emerald');
        const gold = token('--glow-gold');
        const ring = token('--point-ring');
        instance.addSource(SOURCE, {
          type: 'geojson',
          data: collection(latest.current.features),
          cluster: true,
          clusterRadius: 48,
          clusterMaxZoom: 15,
          promoteId: 'id',
        });
        instance.addLayer({
          id: 'clusters',
          type: 'circle',
          source: SOURCE,
          filter: ['has', 'point_count'],
          paint: {
            'circle-color': emerald,
            'circle-opacity': 0.85,
            'circle-radius': ['step', ['get', 'point_count'], 16, 10, 20, 50, 26],
            'circle-stroke-color': gold,
            'circle-stroke-width': 1.5,
          },
        });
        instance.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: SOURCE,
          filter: ['has', 'point_count'],
          layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 13 },
          paint: { 'text-color': '#04130d' },
        });
        instance.addLayer({
          id: 'points',
          type: 'circle',
          source: SOURCE,
          filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': [
              'case',
              ['boolean', ['feature-state', 'selected'], false],
              gold,
              emerald,
            ],
            'circle-radius': ['case', ['boolean', ['feature-state', 'selected'], false], 10, 7],
            'circle-stroke-color': ring,
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
          paint: { 'fill-color': gold, 'fill-opacity': 0.18 },
        });
        instance.addLayer({
          id: 'cell-line',
          type: 'line',
          source: CELL_SOURCE,
          paint: { 'line-color': gold, 'line-width': 1.5 },
        });
        instance.addSource(MARKER_SOURCE, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        instance.addLayer({
          id: 'marker',
          type: 'circle',
          source: MARKER_SOURCE,
          paint: {
            'circle-color': gold,
            'circle-radius': 9,
            'circle-stroke-color': ring,
            'circle-stroke-width': 2,
          },
        });
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
          handlers.current.onMoved?.(windowOf(instance), event.originalEvent !== undefined);
        });
        handlers.current.onMoved?.(windowOf(instance), false);
      });
    });
    return () => {
      cancelled = true;
      ready.current = false;
      map.current?.remove();
      map.current = null;
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
      <p className="pointer-events-none absolute bottom-1 start-1 m-0 rounded bg-[var(--surface-glass)] px-2 py-0.5 text-[0.6875rem] text-fg-muted">
        {A.attribution}
      </p>
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
