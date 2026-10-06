'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { loadProgress, type Progress } from './api';

export type ProgressLoad =
  | { status: 'loading' | 'failed' }
  | { status: 'ready'; progress: Progress; refreshing: boolean };

/**
 * The learner's practice, as the server records it: loaded when the screen
 * opens, again on request, and again quietly when the page comes back into
 * view, so a meaning learned in another tab or on another device lights here.
 * What is on screen stays while a reload runs, and a quiet reload that fails
 * keeps it: a network failure is never shown as an empty sky. «Today» is the
 * device's day, so the time zone is sent with the request; the API falls back
 * to UTC for a name it does not know. Only the latest request may change the
 * screen, so a slow answer never replaces a newer one.
 */
export function useProgress(): { load: ProgressLoad; reload: () => void } {
  const [load, setLoad] = useState<ProgressLoad>({ status: 'loading' });
  const latest = useRef(0);

  const fetchProgress = useCallback((quiet: boolean) => {
    latest.current += 1;
    const request = latest.current;
    setLoad((current) => {
      if (current.status === 'ready') {
        return { ...current, refreshing: true };
      }
      return quiet ? current : { status: 'loading' };
    });
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    void loadProgress(zone).then((result) => {
      if (request !== latest.current) {
        return;
      }
      setLoad((current) => {
        if (result.ok) {
          return { status: 'ready', progress: result.data, refreshing: false };
        }
        if (current.status === 'ready') {
          return { ...current, refreshing: false };
        }
        return { status: 'failed' };
      });
    });
  }, []);

  const reload = useCallback(() => fetchProgress(false), [fetchProgress]);

  useEffect(reload, [reload]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        fetchProgress(true);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchProgress]);

  return { load, reload };
}
