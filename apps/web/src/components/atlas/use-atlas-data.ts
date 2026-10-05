'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { clustersIn, entriesPage } from '@/atlas/api';
import {
  type AtlasFeature,
  type AtlasFilters,
  coarsen,
  coarsePoint,
  type MapFeature,
  MOVE_DEBOUNCE_MS,
  padWindow,
  WINDOW_PADDING,
  type Window,
} from '@/atlas/types';
import type { AtlasView } from '@/atlas/view-state';
import { failureMessage } from '@/lib/api/failure-message';

/*
 * What the atlas shows for a map that moves: the groups and entries the map draws (for a
 * window padded by a quarter on each side, so counts at the edges are whole) and the
 * paginated list of the visible window beside it. Both ask after the map stands still for a
 * moment, cancel the request a newer move outdates, and skip a request whose window, zoom
 * and filters did not change. The map's own features land once per answer, never per move.
 */

export type MapData = {
  features: MapFeature[];
  truncated: boolean;
  status: 'idle' | 'loading' | 'ready' | 'failed';
  message: string | null;
};

export type ListData = {
  items: AtlasFeature[];
  total: number;
  cursor: string | null;
  status: 'idle' | 'loading' | 'ready' | 'failed';
  message: string | null;
  more: 'idle' | 'loading' | 'failed';
};

const FIRST_MAP: MapData = { features: [], truncated: false, status: 'idle', message: null };
const FIRST_LIST: ListData = {
  items: [],
  total: 0,
  cursor: null,
  status: 'idle',
  message: null,
  more: 'idle',
};

function keyOf(window: Window, filters: AtlasFilters, extra: string): string {
  return [
    window.west,
    window.south,
    window.east,
    window.north,
    filters.period,
    filters.country,
    filters.concept,
    extra,
  ].join('|');
}

interface Looking {
  window: Window;
  centre: AtlasView['center'];
  zoom: number;
}

export function useAtlasData(filters: AtlasFilters) {
  const [map, setMap] = useState<MapData>(FIRST_MAP);
  const [list, setList] = useState<ListData>(FIRST_LIST);
  // The grid-snapped centre the list was last asked around: a public map view, never the device's position.
  const [listCentre, setListCentre] = useState<AtlasView['center'] | null>(null);
  const looking = useRef<Looking | null>(null);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const mapKey = useRef<string | null>(null);
  const listKey = useRef<string | null>(null);
  const mapRequest = useRef<AbortController | null>(null);
  const listRequest = useRef<AbortController | null>(null);
  // The window and centre the current cursor belongs to: a cursor is only good for those.
  const page = useRef<{ looking: Looking; cursor: string | null } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const askMap = useCallback(async (seen: Looking, applied: AtlasFilters) => {
    mapRequest.current?.abort();
    const request = new AbortController();
    mapRequest.current = request;
    setMap((previous) => ({ ...previous, status: 'loading', message: null }));
    const result = await clustersIn(
      padWindow(seen.window, WINDOW_PADDING),
      Math.round(seen.zoom),
      applied,
      request.signal
    );
    if (request.signal.aborted) {
      return;
    }
    if (result.ok) {
      setMap({
        features: result.data.features,
        truncated: result.data.truncated,
        status: 'ready',
        message: null,
      });
    } else {
      mapKey.current = null;
      setMap((previous) => ({ ...previous, status: 'failed', message: failureMessage(result) }));
    }
  }, []);

  const askList = useCallback(async (seen: Looking, applied: AtlasFilters) => {
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    setList((previous) => ({ ...previous, status: 'loading', message: null, more: 'idle' }));
    setListCentre(coarsePoint(seen.centre));
    const result = await entriesPage(seen.window, seen.centre, applied, null, request.signal);
    if (request.signal.aborted) {
      return;
    }
    if (result.ok) {
      page.current = { looking: seen, cursor: result.data.next_cursor };
      setList({
        items: result.data.items,
        total: result.data.total,
        cursor: result.data.next_cursor,
        status: 'ready',
        message: null,
        more: 'idle',
      });
    } else {
      listKey.current = null;
      setList((previous) => ({ ...previous, status: 'failed', message: failureMessage(result) }));
    }
  }, []);

  const refresh = useCallback(
    (force = false) => {
      const seen = looking.current;
      if (seen === null) {
        return;
      }
      const applied = filtersRef.current;
      const wide = keyOf(
        coarsen(padWindow(seen.window, WINDOW_PADDING)),
        applied,
        String(Math.round(seen.zoom))
      );
      if (force || wide !== mapKey.current) {
        mapKey.current = wide;
        void askMap(seen, applied);
      }
      const visible = keyOf(coarsen(seen.window), applied, coarsePoint(seen.centre).join(','));
      if (force || visible !== listKey.current) {
        listKey.current = visible;
        void askList(seen, applied);
      }
    },
    [askMap, askList]
  );

  const onMoved = useCallback(
    (window: Window, _byHand: boolean, view: AtlasView) => {
      const first = looking.current === null;
      looking.current = { window, centre: view.center, zoom: view.zoom };
      if (timer.current !== null) {
        clearTimeout(timer.current);
        timer.current = null;
      }
      if (first) {
        refresh();
      } else {
        timer.current = setTimeout(refresh, MOVE_DEBOUNCE_MS);
      }
    },
    [refresh]
  );

  // A filter change asks again for the same view, at once.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `filters` is the trigger; `refresh` reads the latest through a ref.
  useEffect(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    refresh();
  }, [filters, refresh]);

  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
      mapRequest.current?.abort();
      listRequest.current?.abort();
    },
    []
  );

  const loadMore = useCallback(async () => {
    const current = page.current;
    if (current === null || current.cursor === null) {
      return;
    }
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    setList((previous) => ({ ...previous, more: 'loading' }));
    const { window, centre } = current.looking;
    const result = await entriesPage(
      window,
      centre,
      filtersRef.current,
      current.cursor,
      request.signal
    );
    if (request.signal.aborted) {
      return;
    }
    if (result.ok) {
      page.current = { looking: current.looking, cursor: result.data.next_cursor };
      setList((previous) => {
        const known = new Set(previous.items.map((item) => item.id));
        return {
          ...previous,
          items: [...previous.items, ...result.data.items.filter((item) => !known.has(item.id))],
          total: result.data.total,
          cursor: result.data.next_cursor,
          more: 'idle',
        };
      });
    } else {
      setList((previous) => ({ ...previous, more: 'failed' }));
    }
  }, []);

  const retry = useCallback(() => refresh(true), [refresh]);

  return { map, list, listCentre, onMoved, loadMore, retry };
}
