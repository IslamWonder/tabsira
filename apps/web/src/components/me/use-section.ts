'use client';

import { useCallback, useSyncExternalStore } from 'react';

const CHANGE = 'tabsira:me-section';

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  window.addEventListener('popstate', onChange);
  window.addEventListener(CHANGE, onChange);
  return () => {
    window.removeEventListener('hashchange', onChange);
    window.removeEventListener('popstate', onChange);
    window.removeEventListener(CHANGE, onChange);
  };
}

const readHash = () => window.location.hash.slice(1);
const serverHash = () => '';

/**
 * The section of the profile page (/me) that is open, kept in the address (`/me#data`): a link
 * or a shared address opens it, the browser's back button closes it, and
 * nothing is open when the hash names none of the reader's sections. `close`
 * goes back to the whole menu without leaving a bare `#` behind.
 */
export function useOpenSection<T extends string>(
  sections: readonly T[]
): { open: T | null; close: () => void } {
  const hash = useSyncExternalStore(subscribe, readHash, serverHash);
  const open = (sections as readonly string[]).includes(hash) ? (hash as T) : null;
  const close = useCallback(() => {
    window.history.pushState(null, '', window.location.pathname + window.location.search);
    window.dispatchEvent(new Event(CHANGE));
  }, []);
  return { open, close };
}
