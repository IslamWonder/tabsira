'use client';

import { type CSSProperties, type RefObject, useEffect, useRef, useState } from 'react';
import { motionAllowed } from '@/preferences/motion';

export type RevealState = 'waiting' | 'shown';

export interface Reveal<T extends Element> {
  ref: RefObject<T | null>;
  /** Read by fx.css: `waiting` holds the element back, `shown` plays its entrance once. */
  'data-reveal': RevealState | undefined;
}

/**
 * An entrance played when the element first comes into view (motion on display,
 * never on hover). Nothing is ever hidden without a script, or when motion is
 * off, or for what is already on screen at first paint, so the page always reads
 * whole; only what lies below the fold waits for its turn, and plays once.
 */
export function useReveal<T extends Element>(): Reveal<T> {
  const ref = useRef<T>(null);
  const [state, setState] = useState<RevealState | undefined>(undefined);

  useEffect(() => {
    const node = ref.current;
    if (node === null || typeof IntersectionObserver === 'undefined' || !motionAllowed()) {
      return;
    }
    if (node.getBoundingClientRect().top < window.innerHeight) {
      return;
    }
    setState('waiting');
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setState('shown');
          observer.disconnect();
        }
      },
      { rootMargin: '0px 0px -12% 0px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, 'data-reveal': state };
}

/** The inline delay of one item of a revealed group, in reading order. */
export function revealDelay(index: number, step = 120, start = 0): CSSProperties {
  return { '--fx-delay': `${start + index * step}ms` } as CSSProperties;
}
