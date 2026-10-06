import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import { forgetLegal } from '@/account/legal';
import { forgetProviders } from '@/account/providers';
import { forgetSession } from '@/account/session';
import { forgetConsent } from '@/consent/store';
import { forgetIdentity } from '@/social/identity-store';
import { NEVER_ANSWERS } from './api';
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
  // No unit test reaches the network: a request no test described never answers.
  vi.stubGlobal('fetch', vi.fn(NEVER_ANSWERS));
  if (typeof window === 'undefined') {
    return;
  }
  stubMatchMedia();
  // jsdom has no 2D canvas and would log "not implemented"; tests that draw provide their own.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});

afterEach(() => {
  // Unmount before the stores forget: unmounting flushes the effects still queued
  // by the test's tree, and one that found the session already forgotten would
  // ask the API again with this test's mock, for the next test to inherit.
  if (typeof window !== 'undefined') {
    cleanup();
  }
  // What the page learnt from the API, as a fresh page load would have it.
  forgetSession();
  forgetProviders();
  forgetLegal();
  forgetConsent();
  forgetIdentity();
  // Files that run in the node environment (server rendering) have no DOM to reset.
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.clear();
  window.sessionStorage.clear();
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0]?.trim();
    if (name) {
      // biome-ignore lint/suspicious/noDocumentCookie: resetting jsdom's cookie jar between tests.
      document.cookie = `${name}=; Path=/; Max-Age=0`;
    }
  }
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.motion;
  document.documentElement.removeAttribute('style');
});
