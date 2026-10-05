'use client';

import { useEffect, useRef } from 'react';
import { endLoop, loopSound, stopSound } from '@/lib/sound/player';
import { useSoundEnabled } from '@/preferences/sound';

/** Where the run stands, as the scene's sound needs it. */
export type SoundMoment = 'running' | 'ended' | 'failed';

/**
 * The scene's sound loops while the insight is prepared, from the moment the
 * scene is matched to the ontology. When the run ends it finishes its loop;
 * when the run fails it fades out at once; leaving the page fades it out, so
 * it is never heard over a verse. Switched on again during the run, it starts
 * again; after the run, it stays quiet.
 */
export function useSceneSound(url: string | null, moment: SoundMoment): void {
  const enabled = useSoundEnabled();
  const running = useRef(moment === 'running');
  running.current = moment === 'running';

  useEffect(() => {
    if (url === null || !enabled || !running.current) {
      return undefined;
    }
    void loopSound(url);
    return stopSound;
  }, [url, enabled]);

  useEffect(() => {
    if (moment === 'ended') {
      endLoop();
    } else if (moment === 'failed') {
      stopSound();
    }
  }, [moment]);
}
