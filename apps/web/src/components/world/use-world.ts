'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { loadWorld, markRevealsShown, type Place, type World } from '@/world/api';

export type WorldLoad =
  | { status: 'loading' }
  | { status: 'failed' }
  | { status: 'ready'; world: World };

export interface WorldState {
  load: WorldLoad;
  reload: () => void;
  /** Keeps a place the API returned after a visit (its treasure may have just become ready). */
  replacePlace: (place: Place) => void;
  /** The world played these reveals: kept as shown here at once, and told to the API. */
  markShown: (ids: readonly string[]) => void;
}

function withShown(world: World, shown: ReadonlySet<string>): World {
  return {
    ...world,
    reveals: world.reveals.map((reveal) =>
      shown.has(reveal.id) ? { ...reveal, shown: true } : reveal
    ),
  };
}

/**
 * The learner's world, as the server keeps it (decision 59): loaded when the
 * screen opens, again on request, and again quietly when the page comes back
 * into view, so a reveal earned on another device or another tab shows here.
 * A quiet reload that fails keeps what is on screen; nothing is ever cleared.
 * Reveals played here stay shown even if the API has not heard of it yet.
 */
export function useWorld(): WorldState {
  const [load, setLoad] = useState<WorldLoad>({ status: 'loading' });
  const shown = useRef(new Set<string>());

  const fetchWorld = useCallback((quiet: boolean) => {
    if (!quiet) {
      setLoad({ status: 'loading' });
    }
    void loadWorld().then((result) => {
      if (result.ok) {
        setLoad({ status: 'ready', world: withShown(result.data, shown.current) });
      } else if (!quiet) {
        setLoad({ status: 'failed' });
      }
    });
  }, []);

  const reload = useCallback(() => fetchWorld(false), [fetchWorld]);

  useEffect(reload, [reload]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        fetchWorld(true);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchWorld]);

  const replacePlace = useCallback((place: Place) => {
    setLoad((current) =>
      current.status === 'ready'
        ? {
            status: 'ready',
            world: {
              ...current.world,
              places: current.world.places.map((item) => (item.id === place.id ? place : item)),
            },
          }
        : current
    );
  }, []);

  const markShown = useCallback((ids: readonly string[]) => {
    for (const id of ids) {
      shown.current.add(id);
    }
    setLoad((current) =>
      current.status === 'ready'
        ? { status: 'ready', world: withShown(current.world, shown.current) }
        : current
    );
    // A request that fails only means the effect may play once more on the next visit.
    void markRevealsShown(ids);
  }, []);

  return { load, reload, replacePlace, markShown };
}
