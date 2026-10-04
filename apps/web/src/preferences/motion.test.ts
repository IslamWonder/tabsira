import { describe, expect, it, vi } from 'vitest';
import { stubMatchMedia } from '@/test/media';
import {
  MOTION_STORAGE_KEY,
  motionAllowed,
  readAmbientMotion,
  setAmbientMotion,
  subscribeAmbientMotion,
} from './motion';

describe('decorative motion preference', () => {
  it('is on by default and when storage is blocked', () => {
    expect(readAmbientMotion()).toBe(true);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readAmbientMotion()).toBe(true);
  });

  it('is stored, applied to <html> and announced', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAmbientMotion(listener);
    setAmbientMotion(false);
    expect(window.localStorage.getItem(MOTION_STORAGE_KEY)).toBe('off');
    expect(document.documentElement.dataset.motion).toBe('reduce');
    expect(readAmbientMotion()).toBe(false);
    setAmbientMotion(true);
    expect(window.localStorage.getItem(MOTION_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.hasAttribute('data-motion')).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    setAmbientMotion(false);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('still applies for this visit when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    setAmbientMotion(false);
    expect(document.documentElement.dataset.motion).toBe('reduce');
  });

  it('follows another tab and the device setting', () => {
    const media = stubMatchMedia();
    const listener = vi.fn();
    const unsubscribe = subscribeAmbientMotion(listener);
    window.localStorage.setItem(MOTION_STORAGE_KEY, 'off');
    window.dispatchEvent(new StorageEvent('storage', { key: MOTION_STORAGE_KEY }));
    expect(document.documentElement.dataset.motion).toBe('reduce');
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'other' }));
    media.fire();
    expect(listener).toHaveBeenCalledTimes(3);
    unsubscribe();
    expect(media.listeners.size).toBe(0);
  });

  it('allows motion only when both the reader and the device allow it', () => {
    expect(motionAllowed()).toBe(true);
    setAmbientMotion(false);
    expect(motionAllowed()).toBe(false);
    setAmbientMotion(true);
    stubMatchMedia((query) => query.includes('reduce'));
    expect(motionAllowed()).toBe(false);
  });
});
