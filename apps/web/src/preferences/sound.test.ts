import { renderHook } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it, vi } from 'vitest';
import {
  readSoundEnabled,
  SOUND_STORAGE_KEY,
  setSoundEnabled,
  subscribeSound,
  useSoundEnabled,
} from './sound';

describe('sound effect preference', () => {
  it('is on by default and when storage is blocked', () => {
    expect(readSoundEnabled()).toBe(true);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readSoundEnabled()).toBe(true);
  });

  it('keeps only the off state, and announces each change', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSound(listener);
    setSoundEnabled(false);
    expect(window.localStorage.getItem(SOUND_STORAGE_KEY)).toBe('off');
    expect(readSoundEnabled()).toBe(false);
    setSoundEnabled(true);
    expect(window.localStorage.getItem(SOUND_STORAGE_KEY)).toBeNull();
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    setSoundEnabled(false);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('still announces a change when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const listener = vi.fn();
    subscribeSound(listener);
    setSoundEnabled(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('follows another tab', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSound(listener);
    window.dispatchEvent(new StorageEvent('storage', { key: SOUND_STORAGE_KEY }));
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'other' }));
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('is read by components as it changes', () => {
    window.localStorage.clear();
    const { result } = renderHook(() => useSoundEnabled());
    expect(result.current).toBe(true);
    act(() => setSoundEnabled(false));
    expect(result.current).toBe(false);
    act(() => setSoundEnabled(true));
  });
});
