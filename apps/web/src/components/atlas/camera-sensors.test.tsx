import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  forgetDevice,
  stubCamera,
  stubGeolocation,
  stubOrientation,
  turnDevice,
} from '@/test/camera';
import {
  FIX_MAX_AGE_MS,
  HEADING_STALE_MS,
  HEADING_WAIT_MS,
  useCameraStream,
  useDeviceHeading,
  useDevicePosition,
} from './camera-sensors';

afterEach(() => {
  forgetDevice();
  vi.useRealTimers();
});

describe('useCameraStream', () => {
  it('says when the browser has no camera API or the camera cannot be read', async () => {
    stubCamera('none');
    const { result } = renderHook(() => useCameraStream());
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');

    stubCamera('failed');
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');
  });

  it('lets the tracks go when the screen is left', async () => {
    const { track } = stubCamera('granted');
    const { result, unmount } = renderHook(() => useCameraStream());
    await act(() => result.current.start());
    expect(result.current.state).toBe('live');
    unmount();
    expect(track.stop).toHaveBeenCalledTimes(1);
  });
});

describe('useDevicePosition', () => {
  it('says when the device cannot locate itself at all', () => {
    stubGeolocation(false);
    const { result } = renderHook(() => useDevicePosition());
    act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');
    act(() => result.current.stop());
  });

  it('ignores a reading older than a minute, keeps the fresh one, and reads a missing accuracy as none', () => {
    const geolocation = stubGeolocation();
    const now = () => 1_000_000;
    const { result, unmount } = renderHook(() => useDevicePosition(now));
    act(() => result.current.start());
    geolocation.fix([10, 36], 12, now() - FIX_MAX_AGE_MS - 1);
    expect(result.current.fix).toBeNull();
    expect(result.current.state).toBe('locating');
    geolocation.fix([10, 36], Number.NaN, now());
    expect(result.current.fix).toEqual({ center: [10, 36], accuracyM: null, at: now() });
    expect(result.current.state).toBe('ready');
    geolocation.fail(2);
    expect(result.current.state).toBe('unavailable');
    unmount();
    expect(geolocation.clearWatch).toHaveBeenCalledWith(7);
  });
});

describe('useDeviceHeading', () => {
  it('has nothing to offer without orientation events', async () => {
    vi.stubGlobal('DeviceOrientationEvent', undefined);
    const { result } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    expect(result.current.state).toBe('unavailable');
  });

  it('asks Safari for permission on the tap and takes no for an answer', async () => {
    const denied = stubOrientation('denied');
    const { result } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    expect(denied.requestPermission).toHaveBeenCalled();
    expect(result.current.state).toBe('denied');

    stubOrientation('throws');
    await act(() => result.current.enable());
    expect(result.current.state).toBe('denied');

    stubOrientation('granted');
    await act(() => result.current.enable());
    expect(result.current.state).toBe('waiting');
    turnDevice({ alpha: null, webkitCompassHeading: 45 });
    expect(result.current.state).toBe('ready');
    expect(result.current.heading).toBe(45);
  });

  it('gives up waiting for a reading anchored to north, and drops a heading that stops arriving', async () => {
    vi.useFakeTimers();
    stubOrientation();
    const { result, unmount } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    act(() => {
      vi.advanceTimersByTime(HEADING_WAIT_MS);
    });
    expect(result.current.state).toBe('unavailable');

    await act(() => result.current.enable());
    turnDevice({ alpha: 270 });
    expect(result.current.heading).toBeCloseTo(90);
    // Readings come faster than renders; the smoothed value follows, the renders are paced.
    turnDevice({ alpha: 250 });
    expect(result.current.heading).toBeCloseTo(90);
    act(() => {
      vi.advanceTimersByTime(HEADING_STALE_MS);
    });
    expect(result.current.state).toBe('stale');
    expect(result.current.heading).toBeNull();
    unmount();
  });
});
