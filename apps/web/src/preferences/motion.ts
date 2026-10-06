'use client';

import { useSyncExternalStore } from 'react';
import { MOTION_STORAGE_KEY } from './motion-key';

export { MOTION_STORAGE_KEY } from './motion-key';

/**
 * Decorative motion (the light motes behind every page and the burst on
 * the done button) can be switched off in the profile page, per device. Off sets data-motion on
 * <html>, which globals.css treats exactly like the device's reduced-motion
 * setting. The device setting always wins: motion is allowed only when both
 * allow it. This is the pause control WCAG 2.2.2 asks for, since the motes
 * keep moving for longer than five seconds.
 */

const CHANGE_EVENT = 'tabsira:motion-change';
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

export function readAmbientMotion(): boolean {
  try {
    return window.localStorage.getItem(MOTION_STORAGE_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function applyAmbientMotion(on: boolean): void {
  if (on) {
    document.documentElement.removeAttribute('data-motion');
  } else {
    document.documentElement.setAttribute('data-motion', 'reduce');
  }
}

export function setAmbientMotion(on: boolean): void {
  try {
    if (on) {
      window.localStorage.removeItem(MOTION_STORAGE_KEY);
    } else {
      window.localStorage.setItem(MOTION_STORAGE_KEY, 'off');
    }
  } catch {
    // Not stored, but still applied for this visit.
  }
  applyAmbientMotion(on);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Calls `onChange` after a change made here, in another tab, or in the device setting. */
export function subscribeAmbientMotion(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === MOTION_STORAGE_KEY || event.key === null) {
      applyAmbientMotion(readAmbientMotion());
      onChange();
    }
  };
  const query = window.matchMedia(REDUCED_MOTION);
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, onChange);
  query.addEventListener('change', onChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, onChange);
    query.removeEventListener('change', onChange);
  };
}

/** Whether decorative motion may run now: the reader's choice and the device's both allow it. */
export function motionAllowed(): boolean {
  return readAmbientMotion() && !window.matchMedia(REDUCED_MOTION).matches;
}

function serverSnapshot(): boolean {
  return true;
}

/** The reader's own choice (not the device's), for the switch in the profile page. */
export function useAmbientMotion(): boolean {
  return useSyncExternalStore(subscribeAmbientMotion, readAmbientMotion, serverSnapshot);
}
