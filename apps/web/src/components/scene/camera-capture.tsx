'use client';

import { type ChangeEvent, useEffect, useId, useState } from 'react';
import { useCameraStream } from '@/components/atlas/camera-sensors';
import { CameraIcon } from '@/components/icons';
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
  return new File([blob], `capture-${now()}.jpg`, { type: 'image/jpeg', lastModified: now() });
}

/**
 * Take a photo in the page, as the earlier prototype did: the back camera as a
 * live preview, one shutter, one JPEG handed to the owner. The frame goes
 * nowhere else: the stream stops as soon as the photo is taken or the view is
 * closed. Where the page cannot open a camera (no device, refused, a plain
 * http page), the native picker with `capture` takes over, which on a phone
 * opens its camera app.
 */
export type CameraAvailability = 'unknown' | 'available' | 'none' | 'denied';

/**
 * What the device says before any camera is asked for: whether a video input
 * exists (`enumerateDevices` lists devices without their labels until a
 * permission is given) and whether the camera permission was already refused.
 * A machine without a webcam, or a refusal remembered by the browser, is then
 * known at once and the fallback shows without a tap that would fail.
 */
export function useCameraAvailability(secure: boolean): CameraAvailability {
  const [availability, setAvailability] = useState<CameraAvailability>('unknown');

  useEffect(() => {
    const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices;
    if (!secure || devices === undefined || typeof devices.getUserMedia !== 'function') {
      setAvailability('none');
      return;
    }
    let cancelled = false;
    const look = async () => {
      let found: CameraAvailability = 'unknown';
      if (typeof devices.enumerateDevices === 'function') {
        try {
          const list = await devices.enumerateDevices();
          found = list.some((device) => device.kind === 'videoinput') ? 'available' : 'none';
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
        setAvailability(found);
      }
    };
    void look();
    // A webcam plugged in or removed changes the answer.
    const onChange = () => void look();
    devices.addEventListener?.('devicechange', onChange);
    return () => {
      cancelled = true;
      devices.removeEventListener?.('devicechange', onChange);
    };
  }, [secure]);

  return availability;
}

export function CameraCapture({ onFile, onPick }: CameraCaptureProps) {
  const camera = useCameraStream();
  const [taking, setTaking] = useState(false);
  const [failed, setFailed] = useState(false);
  const inputId = useId();
  const text = messages.scene.starter;
  const secure = typeof window === 'undefined' || window.isSecureContext !== false;
  const availability = useCameraAvailability(secure);
  const denied = camera.state === 'denied' || availability === 'denied';
  const fallback = !secure || denied || camera.state === 'unavailable' || availability === 'none';

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

  if (fallback) {
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
          {!secure ? text.cameraNeedsHttps : denied ? text.cameraDenied : text.cameraUnavailable}
        </p>
      </div>
    );
  }

  if (camera.state === 'idle' || camera.state === 'paused') {
    return (
      <Button variant="secondary" onClick={() => void camera.start()}>
        <CameraIcon width="18" height="18" />
        {text.camera}
      </Button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="relative overflow-hidden rounded-[18px] bg-black">
        <video
          ref={camera.videoRef}
          playsInline
          muted
          autoPlay
          aria-label={text.cameraPreview}
          className="block aspect-[4/3] w-full object-cover"
        />
        {camera.state === 'starting' ? (
          <p
            role="status"
            className="absolute inset-0 m-0 flex items-center justify-center bg-black/40 text-sm text-white"
          >
            {text.cameraStarting}
          </p>
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
