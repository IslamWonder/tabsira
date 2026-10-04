'use client';

import { useEffect, useState } from 'react';

export interface BoxSize {
  readonly width: number;
  readonly height: number;
}

/** Measures an element and follows its size; null until the first measurement. */
export function useBoxSize(element: HTMLElement | null): BoxSize | null {
  const [size, setSize] = useState<BoxSize | null>(null);
  useEffect(() => {
    if (element === null) {
      return;
    }
    const measure = () => setSize({ width: element.clientWidth, height: element.clientHeight });
    measure();
    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return size;
}
