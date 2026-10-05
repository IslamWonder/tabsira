'use client';

import { useEffect } from 'react';
import { armAudioUnlock } from '@/lib/sound/player';

/**
 * Lets the insight's sound play when it arrives: the first tap or key of the
 * visit (often the one that opens the camera) unlocks the page's audio.
 */
export function AudioUnlock() {
  useEffect(() => {
    armAudioUnlock();
  }, []);
  return null;
}
