import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MOTION_STORAGE_KEY } from '@/preferences/motion';
import { stubMatchMedia } from '@/test/media';
import { revealDelay, useReveal } from './use-reveal';

function Section() {
  const reveal = useReveal<HTMLDivElement>();
  return (
    <div {...reveal} data-testid="section">
      [قسم]
    </div>
  );
}

let observed: { callback: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }[] =
  [];

/** jsdom has no IntersectionObserver: this one is told by the test when the section shows. */
function stubObserver() {
  observed = [];
  window.IntersectionObserver = class {
    disconnect = vi.fn();
    observe = vi.fn();
    unobserve = vi.fn();
    takeRecords = () => [];
    constructor(callback: IntersectionObserverCallback) {
      observed.push({ callback, disconnect: this.disconnect });
    }
  } as unknown as typeof IntersectionObserver;
}

/** Where the section sits at first paint: its top edge, in pixels from the window's top. */
function placeAt(top: number) {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    top,
  } as DOMRect);
}

const show = (isIntersecting: boolean) =>
  act(() =>
    observed[0]?.callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      {} as IntersectionObserver
    )
  );

beforeEach(() => {
  stubObserver();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem(MOTION_STORAGE_KEY);
  stubMatchMedia();
  Reflect.deleteProperty(window, 'IntersectionObserver');
});

describe('useReveal', () => {
  it('holds back a section below the fold, and plays its entrance once it comes into view', () => {
    placeAt(window.innerHeight + 200);
    render(<Section />);
    const section = screen.getByTestId('section');
    expect(section).toHaveAttribute('data-reveal', 'waiting');
    show(false);
    expect(section).toHaveAttribute('data-reveal', 'waiting');
    show(true);
    expect(section).toHaveAttribute('data-reveal', 'shown');
    expect(observed[0]?.disconnect).toHaveBeenCalled();
  });

  it('never hides what is already on screen at first paint', () => {
    placeAt(40);
    render(<Section />);
    expect(screen.getByTestId('section')).not.toHaveAttribute('data-reveal');
    expect(observed).toHaveLength(0);
  });

  it('hides nothing when motion is off, on the device or in the profile page', () => {
    placeAt(window.innerHeight + 200);
    stubMatchMedia((query) => query.includes('reduce'));
    const { unmount } = render(<Section />);
    expect(screen.getByTestId('section')).not.toHaveAttribute('data-reveal');
    unmount();

    stubMatchMedia();
    window.localStorage.setItem(MOTION_STORAGE_KEY, 'off');
    render(<Section />);
    expect(screen.getByTestId('section')).not.toHaveAttribute('data-reveal');
  });

  it('hides nothing in a browser without IntersectionObserver', () => {
    placeAt(window.innerHeight + 200);
    Reflect.deleteProperty(window, 'IntersectionObserver');
    render(<Section />);
    expect(screen.getByTestId('section')).not.toHaveAttribute('data-reveal');
  });

  it('stops watching when the section leaves the page', () => {
    placeAt(window.innerHeight + 200);
    const { unmount } = render(<Section />);
    unmount();
    expect(observed[0]?.disconnect).toHaveBeenCalled();
  });
});

describe('revealDelay', () => {
  it('spaces the items of a group in reading order, after an optional start', () => {
    expect(revealDelay(0)).toEqual({ '--fx-delay': '0ms' });
    expect(revealDelay(2, 150, 300)).toEqual({ '--fx-delay': '600ms' });
  });
});
