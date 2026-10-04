import { vi } from 'vitest';

/** jsdom has no matchMedia: every query answers false unless a test says otherwise. */
export function stubMatchMedia(matches: (query: string) => boolean = () => false) {
  const listeners = new Set<() => void>();
  window.matchMedia = vi.fn((query: string) => ({
    matches: matches(query),
    media: query,
    onchange: null,
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  const fire = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  return { fire, listeners };
}
