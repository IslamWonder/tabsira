'use client';

import { type ChangeEvent, useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import { type CameraFailure, useCameraStream } from '@/components/atlas/camera-sensors';
import { CameraIcon, SwitchCameraIcon } from '@/components/icons';
import { Button, buttonClasses } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';

export interface CameraCaptureProps {
  onFile: (file: File) => void;
  /** Called with a picked file when the live camera is not available (the native picker). */
  onPick: (event: ChangeEvent<HTMLInputElement>) => void;
}

/** The longest side of a captured photo: enough for the scene, small enough to send. */
export const CAPTURE_MAX_SIDE = 1600;
export const CAPTURE_QUALITY = 0.9;

/** Draw the current video frame and return it as a JPEG file; null when nothing was drawn. */
export async function frameToFile(
  video: HTMLVideoElement,
  now: () => number
): Promise<File | null> {
  // The stream's own pixels, not the size the page draws the video at.
  const width = video.videoWidth || 0;
  const height = video.videoHeight || 0;
  if (width === 0 || height === 0) {
    return null;
  }
  const scale = Math.min(1, CAPTURE_MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  if (context === null) {
    return null;
  }
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', CAPTURE_QUALITY)
  );
  if (blob === null) {
    return null;
  }
  return new File([blob], `tabsira-capture-${now()}.jpg`, {
    type: 'image/jpeg',
    lastModified: now(),
  });
}

/**
 * Take a photo in the page, as the earlier prototype did: the back camera as a
 * live preview, one shutter, one JPEG handed to the owner, which sends it the
 * way it sends a chosen file. The frame goes nowhere else: the stream stops as
 * soon as the photo is taken or the view is closed. Where the page cannot open
 * a camera (no device, refused, a plain http page), the native picker with
 * `capture` takes over, which on a phone opens its camera app, and the reason
 * is said under it.
 */
export type CameraAvailability = 'unknown' | 'available' | 'none' | 'denied' | 'unsupported';

export interface CameraLook {
  availability: CameraAvailability;
  /** How many cameras the device lists: the switch shows from two. */
  cameras: number;
}

/**
 * What the device says before any camera is asked for: whether a video input
 * exists (`enumerateDevices` lists devices without their labels until a
 * permission is given) and whether the camera permission was already refused.
 * A machine without a webcam, or a refusal remembered by the browser, is then
 * known at once and the fallback shows without a tap that would fail. `live`
 * asks once more when the camera runs: some browsers list a single camera
 * until a permission is given.
 */
export function useCameraAvailability(secure: boolean, live = false): CameraLook {
  const [look, setLook] = useState<CameraLook>({ availability: 'unknown', cameras: 0 });

  // biome-ignore lint/correctness/useExhaustiveDependencies: `live` is a trigger; the list is read again once the camera runs.
  useEffect(() => {
    const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
    if (!secure || devices === undefined || typeof devices.getUserMedia !== 'function') {
      setLook({ availability: 'unsupported', cameras: 0 });
      return;
    }
    let cancelled = false;
    const read = async () => {
      let found: CameraAvailability = 'unknown';
      let cameras = 0;
      if (typeof devices.enumerateDevices === 'function') {
        try {
          const list = await devices.enumerateDevices();
          cameras = list.filter((device) => device.kind === 'videoinput').length;
          found = cameras > 0 ? 'available' : 'none';
        } catch {
          found = 'unknown';
        }
      }
      if (found !== 'none' && typeof navigator.permissions?.query === 'function') {
        try {
          // Not every browser knows the camera permission name; a refusal here means nothing.
          const status = await navigator.permissions.query({ name: 'camera' as PermissionName });
          if (status.state === 'denied') {
            found = 'denied';
          }
        } catch {
          // Unknown permission name: the tap decides.
        }
      }
      if (!cancelled) {
        setLook({ availability: found, cameras });
      }
    };
    void read();
    // A webcam plugged in or removed changes the answer.
    const onChange = () => void read();
    devices.addEventListener?.('devicechange', onChange);
    return () => {
      cancelled = true;
      devices.removeEventListener?.('devicechange', onChange);
    };
  }, [secure, live]);

  return look;
}

const neverChanges = () => () => {};
const pageIsSecure = () => window.isSecureContext !== false;
// The server cannot know the page's scheme: it renders the secure branch and the
// client corrects it right after hydration, so both first renders match.
const serverIsSecure = () => true;

/** What keeps the live camera closed, from what the page knew before a tap and what the tap answered. */
export function cameraProblem(
  secure: boolean,
  failure: CameraFailure | null,
  availability: CameraAvailability
): CameraFailure | null {
  if (!secure) {
    return 'insecure';
  }
  if (failure !== null) {
    return failure;
  }
  switch (availability) {
    case 'denied':
      return 'denied';
    case 'none':
      return 'missing';
    case 'unsupported':
      return 'unsupported';
    default:
      return null;
  }
}

const PROBLEM_TEXT: Record<CameraFailure, string> = {
  denied: messages.scene.starter.cameraDenied,
  missing: messages.scene.starter.cameraMissing,
  busy: messages.scene.starter.cameraBusy,
  insecure: messages.scene.starter.cameraNeedsHttps,
  unsupported: messages.scene.starter.cameraUnavailable,
};

export function CameraCapture({ onFile, onPick }: CameraCaptureProps) {
  const camera = useCameraStream();
  const [taking, setTaking] = useState(false);
  const [failed, setFailed] = useState(false);
  const inputId = useId();
  const text = messages.scene.starter;
  const secure = useSyncExternalStore(neverChanges, pageIsSecure, serverIsSecure);
  const { availability, cameras } = useCameraAvailability(secure, camera.state === 'live');
  const problem = cameraProblem(secure, camera.failure, availability);
  const viewRef = useRef<HTMLDivElement>(null);
  const starting = camera.state === 'starting';

  // The preview and its shutter come into sight when the camera opens: in a sheet or a
  // panel that scrolls, they would otherwise open below the fold. Instant, never animated.
  useEffect(() => {
    if (starting) {
      viewRef.current?.scrollIntoView?.({ block: 'nearest' });
    }
  }, [starting]);

  const open = () => {
    setFailed(false);
    void camera.start();
  };

  const shoot = async () => {
    const video = camera.videoRef.current;
    if (video === null || camera.state !== 'live') {
      return;
    }
    setTaking(true);
    const file = await frameToFile(video, Date.now);
    setTaking(false);
    if (file === null) {
      setFailed(true);
      return;
    }
    camera.stop();
    onFile(file);
  };

  // A busy camera may be free a moment later: the live button stays, with the reason under it.
  if (problem !== null && problem !== 'busy') {
    return (
      <div className="flex flex-col gap-2">
        <label
          htmlFor={inputId}
          className={cx(
            buttonClasses('secondary'),
            'cursor-pointer has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-offset-2'
          )}
        >
          <CameraIcon width="18" height="18" />
          {text.camera}
          <input
            id={inputId}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={onPick}
          />
        </label>
        <p className="m-0 text-fg-muted text-sm leading-relaxed" role="status">
          {`${PROBLEM_TEXT[problem]} ${text.cameraFallback}`}
        </p>
      </div>
    );
  }

  if (camera.state !== 'starting' && camera.state !== 'live') {
    return (
      <div className="flex flex-col gap-2">
        <Button variant="secondary" onClick={open}>
          <CameraIcon width="18" height="18" />
          {text.camera}
        </Button>
        {problem === 'busy' ? (
          <p className="m-0 text-fg-muted text-sm leading-relaxed" role="status">
            {PROBLEM_TEXT.busy}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div ref={viewRef} className="flex w-full flex-col gap-3">
      <div className="relative overflow-hidden rounded-[18px] bg-black">
        <video
          ref={camera.videoRef}
          playsInline
          muted
          autoPlay
          aria-label={text.cameraPreview}
          className={cx(
            'block aspect-[4/3] max-h-[50dvh] w-full object-cover',
            // The front camera shows a mirror, as a phone does; the photo itself is not mirrored.
            camera.facing === 'user' && '-scale-x-100'
          )}
        />
        {camera.state === 'starting' ? (
          <p
            role="status"
            className="absolute inset-0 m-0 flex items-center justify-center bg-black/40 text-sm text-white"
          >
            {text.cameraStarting}
          </p>
        ) : null}
        {/* On the preview itself, as on a phone's camera: the shutter row stays one line on a narrow screen. */}
        {cameras > 1 && camera.state === 'live' ? (
          <Button
            variant="icon"
            label={text.cameraSwitch}
            onClick={() => void camera.start(camera.facing === 'user' ? 'environment' : 'user')}
            className="absolute end-2 top-2"
          >
            <SwitchCameraIcon />
          </Button>
        ) : null}
      </div>
      {failed ? (
        <p role="alert" className="m-0 text-danger text-sm">
          {text.captureFailed}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        <Button
          variant="primary"
          onClick={() => void shoot()}
          disabled={camera.state !== 'live' || taking}
          aria-label={text.shutter}
        >
          <CameraIcon width="18" height="18" />
          {text.shutter}
        </Button>
        <Button variant="ghost" onClick={camera.stop} className="border border-line">
          {text.cameraClose}
        </Button>
      </div>
    </div>
  );
}
