'use client';

import { type RefObject, useCallback, useEffect, useRef, useState } from 'react';
import { cameraHeading, type LngLat, type OrientationReading, smoothHeading } from '@/atlas/geo';

/*
 * The three device sources of the camera discovery, each behind the browser's
 * own permission prompt and each started by a tap (extension §7): the back
 * camera, shown and never read, the position, kept on the device, and the
 * orientation sensors, for the heading of the camera. Everything stops when
 * the screen is left or hidden, and starts again only on a request.
 */

export type CameraState = 'idle' | 'starting' | 'live' | 'paused' | 'denied' | 'unavailable';

/** Which camera to ask for: the back one by default, the front one on request. */
export type CameraFacing = 'environment' | 'user';

/**
 * Why the camera did not start, as the reader needs to hear it: refused,
 * no camera, a camera held by another application, a page that is not a
 * secure context (the browser hides the camera API there), or a browser
 * without the API.
 */
export type CameraFailure = 'denied' | 'missing' | 'busy' | 'insecure' | 'unsupported';

export interface CameraStream {
  state: CameraState;
  /** Set while `state` is 'denied' or 'unavailable'. */
  failure: CameraFailure | null;
  facing: CameraFacing;
  videoRef: RefObject<HTMLVideoElement | null>;
  start: (facing?: CameraFacing) => Promise<void>;
  stop: () => void;
}

function stopTracks(stream: MediaStream | null) {
  for (const track of stream?.getTracks() ?? []) {
    track.stop();
  }
}

/** The failure a `getUserMedia` error names (MDN: the DOMException names it may throw). */
export function cameraFailureOf(error: unknown): CameraFailure {
  const name = error instanceof Error ? error.name : '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'denied';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'missing';
    case 'NotReadableError':
    case 'AbortError':
      return 'busy';
    default:
      return 'unsupported';
  }
}

/** The back camera as a live `<video>`: no frame is ever drawn, read or sent. */
export function useCameraStream(): CameraStream {
  const [state, setState] = useState<CameraState>('idle');
  const [failure, setFailure] = useState<CameraFailure | null>(null);
  const [facing, setFacing] = useState<CameraFacing>('environment');
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // Each start and each stop takes a new number: a stream granted after the
  // camera was closed, or after a newer start, is stopped instead of shown.
  const attemptRef = useRef(0);
  // A start waiting for its stream: hiding the page then must cancel it too,
  // or a grant arriving while the page is hidden would light the camera.
  const pendingRef = useRef(false);

  // Lets the camera go without saying anything about the state: the callers do.
  const release = useCallback(() => {
    attemptRef.current += 1;
    pendingRef.current = false;
    stopTracks(streamRef.current);
    streamRef.current = null;
    if (videoRef.current !== null) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const stop = useCallback(() => {
    release();
    setFailure(null);
    setState('idle');
  }, [release]);

  const fail = useCallback((reason: CameraFailure) => {
    setFailure(reason);
    setState(reason === 'denied' ? 'denied' : 'unavailable');
  }, []);

  const start = useCallback(
    async (wanted: CameraFacing = 'environment') => {
      const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
      if (devices === undefined || typeof devices.getUserMedia !== 'function') {
        fail(window.isSecureContext === false ? 'insecure' : 'unsupported');
        return;
      }
      // One stream at a time: a phone refuses a second camera while the first still holds it.
      release();
      const attempt = attemptRef.current;
      pendingRef.current = true;
      setFailure(null);
      setState('starting');
      try {
        const stream = await devices.getUserMedia({
          video: { facingMode: { ideal: wanted } },
          audio: false,
        });
        if (attempt !== attemptRef.current) {
          stopTracks(stream);
          return;
        }
        streamRef.current = stream;
        setFacing(wanted);
        if (videoRef.current !== null) {
          videoRef.current.srcObject = stream;
          // Autoplay may still be refused; the video then shows its first frame when the reader taps.
          await videoRef.current.play().catch(() => undefined);
        }
        setState('live');
      } catch (error) {
        if (attempt === attemptRef.current) {
          fail(cameraFailureOf(error));
        }
      } finally {
        if (attempt === attemptRef.current) {
          pendingRef.current = false;
        }
      }
    },
    [fail, release]
  );

  useEffect(() => {
    const onVisibility = () => {
      if (
        document.visibilityState === 'hidden' &&
        (streamRef.current !== null || pendingRef.current)
      ) {
        release();
        setState('paused');
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      release();
    };
  }, [release]);

  return { state, failure, facing, videoRef, start, stop };
}

export type PositionState = 'idle' | 'locating' | 'ready' | 'denied' | 'unavailable';

export interface Fix {
  center: LngLat;
  /** The radius of error the device reported, in metres; null when it gave none. */
  accuracyM: number | null;
  /** When the reading was taken (the device's clock, in ms). */
  at: number;
}

export interface DevicePosition {
  state: PositionState;
  fix: Fix | null;
  start: () => void;
  stop: () => void;
}

/** A reading older than this is a memory, not a position (extension §7: a limit on the age of readings). */
export const FIX_MAX_AGE_MS = 60_000;

/** The device's position, watched while the screen is open and never sent as such. */
export function useDevicePosition(now: () => number = Date.now): DevicePosition {
  const [state, setState] = useState<PositionState>('idle');
  const [fix, setFix] = useState<Fix | null>(null);
  const watchRef = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (watchRef.current !== null && typeof navigator !== 'undefined' && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchRef.current);
    }
    watchRef.current = null;
  }, []);

  const start = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setState('unavailable');
      return;
    }
    stop();
    setState('locating');
    watchRef.current = navigator.geolocation.watchPosition(
      (position) => {
        if (now() - position.timestamp > FIX_MAX_AGE_MS) {
          return;
        }
        const accuracy = position.coords.accuracy;
        setFix({
          center: [position.coords.longitude, position.coords.latitude],
          accuracyM: Number.isFinite(accuracy) && accuracy > 0 ? accuracy : null,
          at: position.timestamp,
        });
        setState('ready');
      },
      (error) => {
        setState(error.code === error.PERMISSION_DENIED ? 'denied' : 'unavailable');
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 }
    );
  }, [now, stop]);

  useEffect(() => stop, [stop]);

  return { state, fix, start, stop };
}

export type HeadingState = 'idle' | 'waiting' | 'ready' | 'stale' | 'denied' | 'unavailable';

export interface DeviceHeading {
  state: HeadingState;
  /** Where the camera points, clockwise from north, smoothed; null unless `state` is ready. */
  heading: number | null;
  enable: () => Promise<void>;
}

/** No reading anchored to north within this time: the device gives no heading (level A stays). */
export const HEADING_WAIT_MS = 4_000;
/** No reading for this long: the last heading is not shown as if it were current. */
export const HEADING_STALE_MS = 3_000;
/** Renders are paced to this, whatever the sensor's rate. */
const HEADING_RENDER_MS = 100;

type OrientationEventType = 'deviceorientationabsolute' | 'deviceorientation';

interface OrientationPermission {
  requestPermission?: () => Promise<'granted' | 'denied'>;
}

/**
 * The heading of the back camera from the orientation sensors, requested on a
 * tap (Safari asks for permission then, and only over https). A relative
 * reading is never shown as a heading.
 */
export function useDeviceHeading(): DeviceHeading {
  const [state, setState] = useState<HeadingState>('idle');
  const [heading, setHeading] = useState<number | null>(null);
  const smoothed = useRef<number | null>(null);
  const renderedAt = useRef(0);
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => () => cleanup.current?.(), []);

  const enable = useCallback(async () => {
    if (typeof window === 'undefined' || window.DeviceOrientationEvent === undefined) {
      setState('unavailable');
      return;
    }
    const request = (window.DeviceOrientationEvent as unknown as OrientationPermission)
      .requestPermission;
    if (typeof request === 'function') {
      try {
        if ((await request.call(window.DeviceOrientationEvent)) !== 'granted') {
          setState('denied');
          return;
        }
      } catch {
        setState('denied');
        return;
      }
    }
    cleanup.current?.();
    setState('waiting');
    smoothed.current = null;
    setHeading(null);

    let staleTimer: ReturnType<typeof setTimeout> | null = null;
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const waitTimer = setTimeout(() => setState('unavailable'), HEADING_WAIT_MS);
    const flush = () => {
      flushTimer = null;
      renderedAt.current = Date.now();
      setHeading(smoothed.current);
      setState('ready');
    };
    const onReading = (event: Event) => {
      const reading = event as unknown as OrientationReading;
      const angle = window.screen.orientation?.angle ?? 0;
      const next = cameraHeading(reading, angle);
      if (next === null) {
        return;
      }
      clearTimeout(waitTimer);
      if (staleTimer !== null) {
        clearTimeout(staleTimer);
      }
      staleTimer = setTimeout(() => {
        if (flushTimer !== null) {
          clearTimeout(flushTimer);
          flushTimer = null;
        }
        smoothed.current = null;
        setHeading(null);
        setState('stale');
      }, HEADING_STALE_MS);
      smoothed.current = smoothHeading(smoothed.current, next);
      const elapsed = Date.now() - renderedAt.current;
      if (elapsed >= HEADING_RENDER_MS) {
        flush();
      } else {
        // Readings between two renders are smoothed in; the last one is shown when the pace allows.
        flushTimer ??= setTimeout(flush, HEADING_RENDER_MS - elapsed);
      }
    };
    const type: OrientationEventType =
      'ondeviceorientationabsolute' in window ? 'deviceorientationabsolute' : 'deviceorientation';
    window.addEventListener(type, onReading);
    cleanup.current = () => {
      window.removeEventListener(type, onReading);
      clearTimeout(waitTimer);
      if (staleTimer !== null) {
        clearTimeout(staleTimer);
      }
      if (flushTimer !== null) {
        clearTimeout(flushTimer);
      }
      cleanup.current = null;
    };
  }, []);

  return { state, heading, enable };
}
