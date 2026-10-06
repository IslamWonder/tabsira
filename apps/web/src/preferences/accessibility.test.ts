import { renderHook } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CONTRAST,
  LINKS,
  readChoice,
  setChoice,
  subscribeReadingAids,
  TEXT_SIZE,
  useChoice,
} from './accessibility';

const root = document.documentElement;

afterEach(() => {
  for (const name of ['data-text-size', 'data-contrast', 'data-links']) {
    root.removeAttribute(name);
  }
});

describe('reading aids', () => {
  it('start at their defaults, also with a value it does not know or blocked storage', () => {
    expect(readChoice(TEXT_SIZE)).toBe('normal');
    window.localStorage.setItem(TEXT_SIZE.key, 'huge');
    expect(readChoice(TEXT_SIZE)).toBe('normal');
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readChoice(CONTRAST)).toBe('normal');
  });

  it('are stored, applied to <html> and announced; the default is neither stored nor set', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeReadingAids(listener);
    setChoice(TEXT_SIZE, 'larger');
    expect(window.localStorage.getItem(TEXT_SIZE.key)).toBe('larger');
    expect(root.dataset.textSize).toBe('larger');
    setChoice(LINKS, 'underline');
    expect(root.dataset.links).toBe('underline');
    setChoice(TEXT_SIZE, 'normal');
    expect(window.localStorage.getItem(TEXT_SIZE.key)).toBeNull();
    expect(root.hasAttribute('data-text-size')).toBe(false);
    expect(listener).toHaveBeenCalledTimes(3);
    unsubscribe();
    setChoice(CONTRAST, 'more');
    expect(listener).toHaveBeenCalledTimes(3);
  });

  it('still apply for this visit when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setChoice(CONTRAST, 'more');
    expect(root.dataset.contrast).toBe('more');
  });

  it('follow another tab, and ignore the keys that are not theirs', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeReadingAids(listener);
    window.localStorage.setItem(CONTRAST.key, 'more');
    window.dispatchEvent(new StorageEvent('storage', { key: CONTRAST.key }));
    expect(root.dataset.contrast).toBe('more');
    window.localStorage.setItem(LINKS.key, 'underline');
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    expect(root.dataset.links).toBe('underline');
    window.dispatchEvent(new StorageEvent('storage', { key: 'other' }));
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('give a component the current choice', () => {
    const { result } = renderHook(() => useChoice(TEXT_SIZE));
    expect(result.current).toBe('normal');
    act(() => setChoice(TEXT_SIZE, 'large'));
    expect(result.current).toBe('large');
  });
});
