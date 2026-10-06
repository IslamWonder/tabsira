import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LaunchSplash } from '@/components/app/launch-splash';
import { LAUNCH_ATTRIBUTE, LAUNCH_FADE_MS, LAUNCH_KEY, LAUNCH_MS, LAUNCH_SCRIPT } from './launch';

const root = document.documentElement;

/** The device as the script sees it: which media queries match. */
function device({ standalone = true, phone = true, reduced = false } = {}) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches:
      (query.includes('display-mode') && standalone) ||
      (query.includes('max-width') && phone) ||
      (query.includes('reduced-motion') && reduced),
  }));
}

function run() {
  // The exact string <head> runs before the first paint.
  new Function(LAUNCH_SCRIPT)();
}

beforeEach(() => {
  window.sessionStorage.clear();
  root.removeAttribute(LAUNCH_ATTRIBUTE);
  root.removeAttribute('data-motion');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('the launch script', () => {
  it('plays the splash when the installed app opens on a phone, once a window', () => {
    device();
    run();
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(true);
    expect(window.sessionStorage.getItem(LAUNCH_KEY)).toBe('1');
    root.removeAttribute(LAUNCH_ATTRIBUTE);
    run();
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(false);
  });

  it('plays nothing in a browser tab, from tablet up, or with reduced motion', () => {
    for (const setting of [{ standalone: false }, { phone: false }, { reduced: true }]) {
      window.sessionStorage.clear();
      device(setting);
      run();
      expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(false);
    }
    window.sessionStorage.clear();
    device();
    root.setAttribute('data-motion', 'reduce');
    run();
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(false);
  });

  it('counts iOS home screen apps as installed, and survives a missing media API', () => {
    device({ standalone: false });
    vi.stubGlobal('navigator', { ...window.navigator, standalone: true });
    run();
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(true);
    root.removeAttribute(LAUNCH_ATTRIBUTE);
    vi.stubGlobal('matchMedia', undefined);
    expect(run).not.toThrow();
  });
});

describe('LaunchSplash', () => {
  it('is decorative, writes the logo in with the tagline, and ends by itself', () => {
    vi.useFakeTimers();
    root.setAttribute(LAUNCH_ATTRIBUTE, '');
    render(<LaunchSplash />);
    const splash = screen.getByTestId('launch-splash');
    expect(splash).toHaveAttribute('aria-hidden', 'true');
    expect(splash.querySelectorAll('.fx-logo-stroke').length).toBeGreaterThan(0);
    expect(splash).toHaveTextContent('انظر إلى العالم بعين الوحي');
    act(() => vi.advanceTimersByTime(LAUNCH_MS + LAUNCH_FADE_MS));
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(false);
  });

  it('ends at once on a tap', () => {
    root.setAttribute(LAUNCH_ATTRIBUTE, '');
    render(<LaunchSplash />);
    fireEvent.click(screen.getByTestId('launch-splash'));
    expect(root.hasAttribute(LAUNCH_ATTRIBUTE)).toBe(false);
  });

  it('waits for nothing when no launch is playing', () => {
    vi.useFakeTimers();
    render(<LaunchSplash />);
    expect(vi.getTimerCount()).toBe(0);
  });
});
