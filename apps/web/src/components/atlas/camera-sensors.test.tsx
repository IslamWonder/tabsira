import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  forgetDevice,
  hidePage,
  stubCamera,
  stubGeolocation,
  stubOrientation,
  turnDevice,
} from '@/test/camera';
import {
  cameraFailureOf,
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

function CameraProbe() {
  const camera = useCameraStream();
  return (
    <>
      {/* biome-ignore lint/a11y/useMediaCaption: a live camera view has no captions to offer. */}
      <video ref={camera.videoRef} data-testid="video" />
      <p>{camera.state}</p>
      <button type="button" onClick={() => void camera.start()}>
        start
      </button>
      <button type="button" onClick={camera.stop}>
        stop
      </button>
    </>
  );
}

describe('useCameraStream', () => {
  it('shows the stream in the video element it was given, and lets it go on stop', async () => {
    const { track } = stubCamera('granted');
    // Autoplay refused: the stream is still live, its first frame shows on a tap.
    const play = vi
      .spyOn(HTMLMediaElement.prototype, 'play')
      .mockRejectedValue(new Error('NotAllowedError'));
    render(<CameraProbe />);
    await userEvent.click(screen.getByRole('button', { name: 'start' }));
    const video = screen.getByTestId('video') as HTMLVideoElement;
    expect(video.srcObject).not.toBeNull();
    expect(play).toHaveBeenCalled();
    expect(screen.getByText('live')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'stop' }));
    expect(video.srcObject).toBeNull();
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByText('idle')).toBeInTheDocument();
  });

  it('is unavailable without a navigator, and reads a refusal that is not an Error as unavailable', async () => {
    vi.stubGlobal('navigator', undefined);
    const { result } = renderHook(() => useCameraStream());
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');
    vi.unstubAllGlobals();

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: async () => {
          throw 'no camera';
        },
      },
      configurable: true,
    });
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');
  });

  it('does nothing when the page is hidden before the camera started', () => {
    stubCamera('granted');
    const { result } = renderHook(() => useCameraStream());
    hidePage();
    expect(result.current.state).toBe('idle');
  });

  it('says when the browser has no camera API or the camera cannot be read', async () => {
    stubCamera('none');
    const { result } = renderHook(() => useCameraStream());
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');

    expect(result.current.failure).toBe('unsupported');

    stubCamera('failed');
    await act(() => result.current.start());
    expect(result.current.state).toBe('unavailable');
    expect(result.current.failure).toBe('busy');
  });

  it('says a page that is not a secure context hides the camera', async () => {
    stubCamera('none');
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    const { result } = renderHook(() => useCameraStream());
    await act(() => result.current.start());
    expect(result.current.failure).toBe('insecure');
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  });

  it('names each failure of getUserMedia as the reader needs to hear it', () => {
    const named = (name: string) => Object.assign(new Error(name), { name });
    expect(cameraFailureOf(named('NotAllowedError'))).toBe('denied');
    expect(cameraFailureOf(named('SecurityError'))).toBe('denied');
    expect(cameraFailureOf(named('NotFoundError'))).toBe('missing');
    expect(cameraFailureOf(named('OverconstrainedError'))).toBe('missing');
    expect(cameraFailureOf(named('NotReadableError'))).toBe('busy');
    expect(cameraFailureOf(named('AbortError'))).toBe('busy');
    expect(cameraFailureOf(named('TypeError'))).toBe('unsupported');
    expect(cameraFailureOf('not an error')).toBe('unsupported');
  });

  it('stops a stream granted after the camera was closed, and forgets a late refusal', async () => {
    const { getUserMedia, track } = stubCamera('granted');
    let grant: (stream: MediaStream) => void = () => undefined;
    getUserMedia.mockImplementationOnce(
      () => new Promise<MediaStream>((resolve) => (grant = resolve))
    );
    const { result } = renderHook(() => useCameraStream());
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.start();
    });
    expect(result.current.state).toBe('starting');
    act(() => result.current.stop());
    await act(async () => {
      grant({ getTracks: () => [track] } as unknown as MediaStream);
      await pending;
    });
    expect(track.stop).toHaveBeenCalledOnce();
    expect(result.current.state).toBe('idle');

    let refuse: (error: Error) => void = () => undefined;
    getUserMedia.mockImplementationOnce(
      () => new Promise<MediaStream>((_, reject) => (refuse = reject))
    );
    act(() => {
      pending = result.current.start();
    });
    act(() => result.current.stop());
    await act(async () => {
      refuse(Object.assign(new Error('no'), { name: 'NotAllowedError' }));
      await pending;
    });
    expect(result.current.state).toBe('idle');
    expect(result.current.failure).toBeNull();
  });

  it('cancels a start when the page is hidden before the stream is granted', async () => {
    const { getUserMedia, track } = stubCamera('granted');
    let grant: (stream: MediaStream) => void = () => undefined;
    getUserMedia.mockImplementationOnce(
      () => new Promise<MediaStream>((resolve) => (grant = resolve))
    );
    const { result } = renderHook(() => useCameraStream());
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.start();
    });
    hidePage();
    expect(result.current.state).toBe('paused');
    await act(async () => {
      grant({ getTracks: () => [track] } as unknown as MediaStream);
      await pending;
    });
    expect(track.stop).toHaveBeenCalledOnce();
    expect(result.current.state).toBe('paused');
    // Settled, nothing is pending: hiding the page again changes nothing.
    act(() => result.current.stop());
    hidePage();
    expect(result.current.state).toBe('idle');
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

  it('listens for readings anchored to north when the browser offers them as such', async () => {
    stubOrientation();
    Object.defineProperty(window, 'ondeviceorientationabsolute', {
      value: null,
      configurable: true,
    });
    const { result } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    turnDevice({ alpha: 270 });
    expect(result.current.state).toBe('waiting');
    act(() => {
      const event = new Event('deviceorientationabsolute');
      Object.assign(event, { alpha: 270, beta: 90, gamma: 0, absolute: true });
      window.dispatchEvent(event);
    });
    expect(result.current.state).toBe('ready');
    expect(result.current.heading).toBeCloseTo(90);
    Reflect.deleteProperty(window, 'ondeviceorientationabsolute');
  });

  it('drops a paced render that a clock set back would have shown after the heading went stale', async () => {
    vi.useFakeTimers();
    stubOrientation();
    const { result } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    turnDevice({ alpha: 270 });
    expect(result.current.heading).toBeCloseTo(90);
    // The clock jumps back: the next paced render would be due long after the heading is stale.
    vi.setSystemTime(Date.now() - 2 * HEADING_STALE_MS);
    turnDevice({ alpha: 250 });
    act(() => {
      vi.advanceTimersByTime(HEADING_STALE_MS);
    });
    expect(result.current.state).toBe('stale');
    expect(result.current.heading).toBeNull();
    act(() => {
      vi.advanceTimersByTime(2 * HEADING_STALE_MS);
    });
    expect(result.current.state).toBe('stale');
    expect(result.current.heading).toBeNull();
  });

  it('cancels a pending paced render when the screen is left', async () => {
    vi.useFakeTimers();
    stubOrientation();
    const { result, unmount } = renderHook(() => useDeviceHeading());
    await act(() => result.current.enable());
    turnDevice({ alpha: 270 });
    turnDevice({ alpha: 250 });
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
