'use client';

import { useSyncExternalStore } from 'react';

/**
 * The sound effect that plays when an insight opens can be switched off, per
 * device, from the top bar, the insight page and the profile page. It is on
 * until the reader says otherwise: it plays only after their own scan, never
 * on arrival. Only the off state is stored, so clearing the device's data
 * brings the sound back.
 */

export const SOUND_STORAGE_KEY = 'tabsira.sound';
const CHANGE_EVENT = 'tabsira:sound-change';

export function readSoundEnabled(): boolean {
  try {
    return window.localStorage.getItem(SOUND_STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function setSoundEnabled(on: boolean): void {
  try {
    if (on) {
      window.localStorage.removeItem(SOUND_STORAGE_KEY);
    } else {
      window.localStorage.setItem(SOUND_STORAGE_KEY, 'off');
    }
  } catch {
    // Not stored, but still applied for this visit.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Calls `onChange` after a change made here or in another tab. */
export function subscribeSound(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === SOUND_STORAGE_KEY || event.key === null) {
      onChange();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function serverSnapshot(): boolean {
  return true;
}

export function useSoundEnabled(): boolean {
  return useSyncExternalStore(subscribeSound, readSoundEnabled, serverSnapshot);
}
