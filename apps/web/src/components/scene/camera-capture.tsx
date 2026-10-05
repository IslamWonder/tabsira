'use client';

import {
  type ChangeEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { type CameraFailure, useCameraStream } from '@/components/atlas/camera-sensors';
import { SummoningCircle } from '@/components/fx/summoning-circle';
import { CameraIcon, GalleryIcon, SwitchCameraIcon } from '@/components/icons';
import { Button, buttonClasses } from '@/components/ui/button';
import { cx } from '@/lib/cx';
import { messages } from '@/messages';
import { PhotoPicker } from './photo-picker';

export interface CameraCaptureProps {
  onFile: (file: File) => void;
  /** A file from the device's gallery, or from the phone's camera app when the live camera is not available. */
  onPick: (event: ChangeEvent<HTMLInputElement>) => void;
  /**
   * Ask for the camera as soon as this shows, once: for a view opened by the reader's own tap
   * on the capture button, never on a page that merely loads (no permission is asked unprompted).
   */
  autoStart?: boolean;
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

export function CameraCapture({ onFile, onPick, autoStart = false }: CameraCaptureProps) {
  const camera = useCameraStream();
  const [taking, setTaking] = useState(false);
  const [failed, setFailed] = useState(false);
  const text = messages.scene.starter;
  const secure = useSyncExternalStore(neverChanges, pageIsSecure, serverIsSecure);
  const { availability, cameras } = useCameraAvailability(secure, camera.state === 'live');
  const problem = cameraProblem(secure, camera.failure, availability);
  const viewRef = useRef<HTMLDivElement>(null);
  const starting = camera.state === 'starting';
  // Once per mount: the dependencies never change while the view shows. No "already started"
  // flag: React's development double mount cancels the first request with its cleanup, and
  // the second must ask again. A page that is not secure has no camera API: its fallback
  // says why instead.
  useEffect(() => {
    if (autoStart && secure) {
      void camera.start();
    }
  }, [autoStart, secure, camera.start]);

  // The preview and its shutter come into sight when the camera opens: in a sheet or a
  // panel that scrolls, they would otherwise open below the fold. Instant, never animated.
  useEffect(() => {
    if (starting) {
      viewRef.current?.scrollIntoView?.({ block: 'nearest' });
    }
  }, [starting]);

  // Reopened after a pause or a close, the camera the reader last chose comes back.
  const open = () => {
    setFailed(false);
    void camera.start(camera.facing);
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

  const gallery = (
    <PhotoPicker onPick={onPick} className={buttonClasses('secondary', 'lg')}>
      <GalleryIcon width="20" height="20" />
      {text.choose}
    </PhotoPicker>
  );

  // No live camera: the phone's own camera app takes over, the reason said once, plainly.
  if (problem !== null && problem !== 'busy') {
    return (
      <Launcher
        status={`${PROBLEM_TEXT[problem]} ${text.cameraFallback}`}
        camera={
          <PhotoPicker onPick={onPick} capture="environment" className={buttonClasses('cta', 'lg')}>
            <CameraIcon width="20" height="20" />
            {text.camera}
          </PhotoPicker>
        }
        gallery={gallery}
      />
    );
  }

  // Closed, or held by another application: a busy camera may be free a moment later.
  if (camera.state !== 'starting' && camera.state !== 'live') {
    return (
      <Launcher
        status={problem === 'busy' ? PROBLEM_TEXT.busy : null}
        camera={
          <Button variant="cta" size="lg" onClick={open}>
            <CameraIcon width="20" height="20" />
            {text.camera}
          </Button>
        }
        gallery={gallery}
      />
    );
  }

  return (
    <div ref={viewRef} className="flex w-full flex-col gap-4">
      {/* A camera is drawn on black in either theme (the palette has no black: it is written here). */}
      <div className="relative mx-auto aspect-[3/4] max-h-[min(58dvh,560px)] w-full overflow-hidden rounded-[24px] bg-[#000] tablet:aspect-[4/3]">
        <video
          ref={camera.videoRef}
          playsInline
          muted
          autoPlay
          aria-label={text.cameraPreview}
          className={cx(
            'absolute inset-0 size-full object-cover',
            // The front camera shows a mirror, as a phone does; the photo itself is not mirrored.
            camera.facing === 'user' && '-scale-x-100'
          )}
        />
        <ViewfinderFrame />
        {camera.state === 'starting' ? (
          <p
            role="status"
            className="absolute inset-0 m-0 flex items-center justify-center bg-[rgba(0,0,0,0.4)] text-[#fff] text-sm"
          >
            {text.cameraStarting}
          </p>
        ) : (
          <p className="absolute inset-x-4 bottom-3 m-0 text-center text-[#fff] text-sm [text-shadow:0_1px_6px_rgba(0,0,0,0.7)]">
            {text.aim}
          </p>
        )}
        <Button variant="ghost" onClick={camera.stop} className="glass absolute start-3 top-3">
          {text.cameraClose}
        </Button>
      </div>
      {failed ? (
        <p role="alert" className="m-0 text-center text-danger text-sm">
          {text.captureFailed}
        </p>
      ) : null}
      {/* As on a phone's camera: the shutter in the middle of the thumb zone, the gallery and the other camera on its sides. */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <PhotoPicker
          onPick={onPick}
          className="flex min-h-12 flex-col items-center justify-center gap-0.5 justify-self-start rounded-[var(--radius-card)] px-2 text-fg-soft text-xs transition-colors duration-200 hover:text-fg"
        >
          <GalleryIcon width="24" height="24" />
          {text.choose}
        </PhotoPicker>
        <button
          type="button"
          onClick={() => void shoot()}
          disabled={camera.state !== 'live' || taking}
          aria-label={text.shutter}
          className="inline-flex size-[76px] items-center justify-center rounded-full border-4 border-[var(--text)] p-1 transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-50 motion-safe:active:scale-95"
        >
          <span
            aria-hidden="true"
            className="capture-orb inline-flex size-full items-center justify-center rounded-full"
          >
            <CameraIcon width="26" height="26" />
          </span>
        </button>
        {cameras > 1 && camera.state === 'live' ? (
          <Button
            variant="icon"
            label={text.cameraSwitch}
            onClick={() => void camera.start(camera.facing === 'user' ? 'environment' : 'user')}
            className="justify-self-end"
          >
            <SwitchCameraIcon />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** The four corners of a frame over the preview, as a camera draws them; decoration only. */
function ViewfinderFrame() {
  const corner = 'absolute size-7 border-[rgba(255,255,255,0.8)]';
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-5 top-[4.5rem] bottom-11"
    >
      <span className={cx(corner, 'start-0 top-0 rounded-ss-xl border-s-2 border-t-2')} />
      <span className={cx(corner, 'end-0 top-0 rounded-se-xl border-e-2 border-t-2')} />
      <span className={cx(corner, 'start-0 bottom-0 rounded-es-xl border-s-2 border-b-2')} />
      <span className={cx(corner, 'end-0 bottom-0 rounded-ee-xl border-e-2 border-b-2')} />
    </div>
  );
}

interface LauncherProps {
  /** Why the live camera is not showing, or null when it simply has not been opened. */
  status: string | null;
  camera: ReactNode;
  gallery: ReactNode;
}

/** Before the camera runs: the two ways in, full width, the camera first. */
function Launcher({ status, camera, gallery }: LauncherProps) {
  return (
    <div className="flex flex-col items-center gap-4 py-2 text-center">
      <SummoningCircle size={96} />
      {status === null ? null : (
        <p className="m-0 max-w-[34ch] text-fg-soft text-sm leading-relaxed" role="status">
          {status}
        </p>
      )}
      <div className="grid w-full gap-2.5">
        {camera}
        {gallery}
      </div>
    </div>
  );
}
