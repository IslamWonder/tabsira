import { act } from '@testing-library/react';
import { vi } from 'vitest';

/*
 * The device of a unit test: a camera, a position and orientation sensors
 * that answer what the test says. jsdom has none of them; each stub is
 * defined on the navigator or the window and removed again by `forgetDevice`.
 */

export interface FakeTrack {
  stop: ReturnType<typeof vi.fn>;
}

export function stubCamera(outcome: 'granted' | 'denied' | 'failed' | 'none') {
  const track: FakeTrack = { stop: vi.fn() };
  const stream = { getTracks: () => [track] };
  const getUserMedia = vi.fn(async () => {
    if (outcome === 'denied') {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    }
    if (outcome === 'failed') {
      throw Object.assign(new Error('busy'), { name: 'NotReadableError' });
    }
    return stream as unknown as MediaStream;
  });
  Object.defineProperty(navigator, 'mediaDevices', {
    value: outcome === 'none' ? undefined : { getUserMedia },
    configurable: true,
  });
  // jsdom has no media playback; a page's `play()` resolves as a phone's does.
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  return { getUserMedia, track };
}

export interface FakeGeolocation {
  watchPosition: ReturnType<typeof vi.fn>;
  clearWatch: ReturnType<typeof vi.fn>;
  /** Delivers a reading: [longitude, latitude], the accuracy in metres and the reading's time. */
  fix: (point: readonly [number, number], accuracy?: number, timestamp?: number) => void;
  /** Fails the watch; code 1 is a refusal. */
  fail: (code?: number) => void;
}

export function stubGeolocation(present = true): FakeGeolocation {
  let onSuccess: ((position: GeolocationPosition) => void) | null = null;
  let onError: ((error: GeolocationPositionError) => void) | null = null;
  const watchPosition = vi.fn((success: typeof onSuccess, error: typeof onError): number => {
    onSuccess = success;
    onError = error;
    return 7;
  });
  const clearWatch = vi.fn();
  Object.defineProperty(navigator, 'geolocation', {
    value: present ? { watchPosition, clearWatch } : undefined,
    configurable: true,
  });
  return {
    watchPosition,
    clearWatch,
    fix(point, accuracy = 12, timestamp = Date.now()) {
      act(() => {
        onSuccess?.({
          coords: { longitude: point[0], latitude: point[1], accuracy },
          timestamp,
        } as GeolocationPosition);
      });
    },
    fail(code = 1) {
      act(() => {
        onError?.({ code, PERMISSION_DENIED: 1 } as GeolocationPositionError);
      });
    },
  };
}

export interface OrientationStub {
  /** Safari's permission prompt; absent on other browsers. */
  requestPermission?: ReturnType<typeof vi.fn>;
}

/** Gives the window a DeviceOrientationEvent, with Safari's prompt when `permission` is set. */
export function stubOrientation(permission?: 'granted' | 'denied' | 'throws'): OrientationStub {
  class FakeDeviceOrientationEvent extends Event {}
  const stub: OrientationStub = {};
  if (permission !== undefined) {
    stub.requestPermission = vi.fn(async () => {
      if (permission === 'throws') {
        throw new Error('no gesture');
      }
      return permission;
    });
    Object.assign(FakeDeviceOrientationEvent, { requestPermission: stub.requestPermission });
  }
  vi.stubGlobal('DeviceOrientationEvent', FakeDeviceOrientationEvent);
  return stub;
}

/** One reading of the sensors, as the browser would dispatch it. */
export function turnDevice(reading: {
  alpha: number | null;
  beta?: number | null;
  gamma?: number | null;
  absolute?: boolean;
  webkitCompassHeading?: number;
}) {
  act(() => {
    const event = new Event('deviceorientation');
    Object.assign(event, { beta: 90, gamma: 0, absolute: true, ...reading });
    window.dispatchEvent(event);
  });
}

export function forgetDevice() {
  Reflect.deleteProperty(navigator, 'mediaDevices');
  Reflect.deleteProperty(navigator, 'geolocation');
}

/** Hides the page, as switching apps does on a phone. */
export function hidePage() {
  Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
  Reflect.deleteProperty(document, 'visibilityState');
}
