import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import { stubMatchMedia } from './media';

// next/font/local is compiled away by Next.js at build time; outside Next it
// cannot run. Each call returns the shape Next.js gives the module.
vi.mock('next/font/local', () => ({
  default: (options: { variable?: string }) => ({
    className: `font${options.variable ?? ''}`,
    variable: `variable${options.variable ?? ''}`,
    style: { fontFamily: 'test' },
  }),
}));

beforeEach(() => {
  if (typeof window === 'undefined') {
    return;
  }
  stubMatchMedia();
  // jsdom has no 2D canvas and would log "not implemented"; tests that draw provide their own.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});

afterEach(() => {
  // Files that run in the node environment (server rendering) have no DOM to reset.
  if (typeof window === 'undefined') {
    return;
  }
  cleanup();
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('data-motion');
  document.documentElement.removeAttribute('style');
});
