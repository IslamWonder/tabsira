'use client';

import { useCallback, useEffect, useState } from 'react';
import { loadProgress, type Progress } from './api';

export type ProgressLoad =
  | { status: 'loading' | 'failed' }
  | { status: 'ready'; progress: Progress };

/**
 * The learner's practice, loaded once. «Today» is the device's day, so the
 * time zone is sent with the request; the API falls back to UTC for a name it
 * does not know.
 */
export function useProgress(): { load: ProgressLoad; reload: () => void } {
  const [load, setLoad] = useState<ProgressLoad>({ status: 'loading' });

  const reload = useCallback(() => {
    setLoad({ status: 'loading' });
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    void loadProgress(zone).then((result) => {
      setLoad(result.ok ? { status: 'ready', progress: result.data } : { status: 'failed' });
    });
  }, []);

  useEffect(reload, [reload]);

  return { load, reload };
}
