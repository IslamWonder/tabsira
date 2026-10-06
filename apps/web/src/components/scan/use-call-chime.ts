'use client';

import { useEffect, useRef } from 'react';
import { playChime } from '@/lib/sound/player';

/**
 * Chimes once when a run the reader watched stops to ask them something, so a
 * reader who looked away knows the scan waits for them. A scan opened later
 * that already waits stays quiet: nothing changed under the reader's eyes.
 */
export function useCallChime(asking: boolean, running: boolean): void {
  const watched = useRef(false);

  useEffect(() => {
    if (running) {
      watched.current = true;
    }
  }, [running]);

  useEffect(() => {
    if (asking && watched.current) {
      playChime();
    }
  }, [asking]);
}
