'use client';

import { useEffect } from 'react';
import type { Insight } from '@/lib/scan/api';
import { playSound, stopSound } from '@/lib/sound/player';

/**
 * Plays the sound of the insight's main entity once, when the insight has
 * loaded. It depends on the sound's address and not on the insight, so
 * finishing the step or opening the chat (which reload the insight) never
 * plays it again, and leaving the page stops it. The player stays quiet when
 * the reader has switched the sound off.
 */
export function useInsightSound(insight: Insight | null): void {
  const soundUrl = insight?.sound_url ?? null;
  useEffect(() => {
    if (soundUrl === null) {
      return undefined;
    }
    void playSound(soundUrl);
    return stopSound;
  }, [soundUrl]);
}
