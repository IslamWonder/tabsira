'use client';

import { useCallback, useEffect, useState } from 'react';
import { loadWorld, type Place, type World } from '@/world/api';

export type WorldLoad =
  | { status: 'loading' }
  | { status: 'failed' }
  | { status: 'ready'; world: World };

export interface WorldState {
  load: WorldLoad;
  reload: () => void;
  /** Keeps a place the API returned after a visit (its treasure may have just become ready). */
  replacePlace: (place: Place) => void;
}

/** The learner's world, loaded once when the screen opens and again on request. */
export function useWorld(): WorldState {
  const [load, setLoad] = useState<WorldLoad>({ status: 'loading' });

  const reload = useCallback(() => {
    setLoad({ status: 'loading' });
    void loadWorld().then((result) => {
      setLoad(result.ok ? { status: 'ready', world: result.data } : { status: 'failed' });
    });
  }, []);

  useEffect(reload, [reload]);

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

  return { load, reload, replacePlace };
}
