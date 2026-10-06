import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { StrictMode } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { forgetDevice, stubCamera } from '@/test/camera';
import { CameraCapture, cameraProblem, frameToFile, useCameraAvailability } from './camera-capture';

/** jsdom draws nothing: a canvas that hands back a small JPEG, or nothing when asked. */
function stubCanvas(blob: Blob | null = new Blob(['jpeg'], { type: 'image/jpeg' })) {
  const drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage,
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => callback(blob));
  return drawImage;
}

function withFrame(video: HTMLVideoElement, width: number, height: number) {
  Object.defineProperty(video, 'videoWidth', { value: width, configurable: true });
  Object.defineProperty(video, 'videoHeight', { value: height, configurable: true });
}

/** The device list and the remembered permission a page can read before asking for the camera. */
function withDevices(kinds: string[], permission: PermissionState | 'unsupported' = 'prompt') {
  const current = navigator.mediaDevices as MediaDevices | undefined;
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      ...current,
      getUserMedia: current?.getUserMedia,
      enumerateDevices: vi.fn(async () => kinds.map((kind) => ({ kind }) as MediaDeviceInfo)),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
    configurable: true,
  });
  Object.defineProperty(navigator, 'permissions', {
    value:
      permission === 'unsupported'
        ? undefined
        : { query: vi.fn(async () => ({ state: permission }) as PermissionStatus) },
    configurable: true,
  });
}

afterEach(() => {
  forgetDevice();
  Reflect.deleteProperty(navigator, 'permissions');
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  vi.restoreAllMocks();
});

describe('CameraCapture', () => {
  it('opens the camera on a tap, takes one JPEG with the shutter and stops the stream', async () => {
    const { getUserMedia, track } = stubCamera('granted');
    const drawImage = stubCanvas();
    const onFile = vi.fn();
    render(<CameraCapture onFile={onFile} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    const video = await screen.findByLabelText('معاينة الكاميرا');
    withFrame(video as HTMLVideoElement, 4000, 3000);
    const shutter = await screen.findByRole('button', { name: 'التقط' });
    await waitFor(() => expect(shutter).toBeEnabled());

    fireEvent.click(shutter);

    await waitFor(() => expect(onFile).toHaveBeenCalledOnce());
    const file = onFile.mock.calls[0]?.[0] as File;
    expect(file.type).toBe('image/jpeg');
    expect(file.name).toMatch(/^tabsira-capture-\d+\.jpg$/);
    // Scaled to the longest side of 1600, keeping 4:3.
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 1600, 1200);
    expect(track.stop).toHaveBeenCalled();
  });

  it('starts at once when the view was opened by a tap, and only once', async () => {
    const { getUserMedia } = stubCamera('granted');
    const { rerender } = render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} autoStart />);

    expect(await screen.findByLabelText('معاينة الكاميرا')).toBeInTheDocument();
    rerender(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} autoStart />);
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
  });

  it('starts under the development double mount too', async () => {
    const { getUserMedia } = stubCamera('granted');
    render(
      <StrictMode>
        <CameraCapture onFile={vi.fn()} onPick={vi.fn()} autoStart />
      </StrictMode>
    );

    const video = (await screen.findByLabelText('معاينة الكاميرا')) as HTMLVideoElement;
    await waitFor(() => expect(video.srcObject).not.toBeNull());
    expect(getUserMedia).toHaveBeenCalledTimes(2);
  });

  it('waits for a tap when nothing asked it to start', async () => {
    const { getUserMedia } = stubCamera('granted');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    expect(await screen.findByRole('button', { name: /التقط بالكاميرا/ })).toBeInTheDocument();
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('closes the camera without a photo', async () => {
    const { track } = stubCamera('granted');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'أغلق الكاميرا' }));

    expect(track.stop).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /التقط بالكاميرا/ })).toBeInTheDocument();
  });

  it('says so and keeps the camera open when no frame could be drawn', async () => {
    stubCamera('granted');
    stubCanvas(null);
    const onFile = vi.fn();
    render(<CameraCapture onFile={onFile} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    const video = await screen.findByLabelText('معاينة الكاميرا');
    withFrame(video as HTMLVideoElement, 640, 480);
    const shutter = await screen.findByRole('button', { name: 'التقط' });
    await waitFor(() => expect(shutter).toBeEnabled());
    fireEvent.click(shutter);

    expect(await screen.findByRole('alert')).toHaveTextContent('لم تُلتقط الصورة');
    expect(onFile).not.toHaveBeenCalled();
  });

  it('takes no photo when the shutter fires before the camera is live', async () => {
    const { track } = stubCamera('granted');
    const pending = new Promise<MediaStream>(() => {});
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(pending);
    const drawImage = stubCanvas();
    const onFile = vi.fn();
    render(<CameraCapture onFile={onFile} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    const shutter = await screen.findByRole('button', { name: 'التقط' });
    expect(shutter).toBeDisabled();
    // A disabled button gets no click from the browser; the handler itself still refuses.
    const propsKey = Object.keys(shutter).find((key) => key.startsWith('__reactProps'));
    const props = (shutter as unknown as Record<string, { onClick: () => void }>)[propsKey ?? ''];
    await act(async () => {
      props?.onClick();
    });

    expect(drawImage).not.toHaveBeenCalled();
    expect(onFile).not.toHaveBeenCalled();
    expect(track.stop).not.toHaveBeenCalled();
  });

  it('ignores the device list when the view closes before it is read', async () => {
    stubCamera('granted');
    withDevices(['videoinput']);
    let release: (list: MediaDeviceInfo[]) => void = () => {};
    vi.mocked(navigator.mediaDevices.enumerateDevices).mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      })
    );
    const { unmount } = render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);
    unmount();
    await act(async () => {
      release([{ kind: 'videoinput' } as MediaDeviceInfo]);
    });
    expect(navigator.mediaDevices.removeEventListener).toHaveBeenCalled();
  });

  it('reads the device list again when a camera is plugged in or removed', async () => {
    stubCamera('granted');
    withDevices([], 'unsupported');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);
    expect(await screen.findByText(/لم يتم العثور على كاميرا/)).toBeInTheDocument();

    const listener = vi.mocked(navigator.mediaDevices.addEventListener).mock.calls[0]?.[1];
    vi.mocked(navigator.mediaDevices.enumerateDevices).mockResolvedValue([
      { kind: 'videoinput' } as MediaDeviceInfo,
    ]);
    await act(async () => {
      (listener as EventListener)(new Event('devicechange'));
    });
    expect(await screen.findByRole('button', { name: /التقط بالكاميرا/ })).toBeInTheDocument();
  });

  it('reports the camera as unsupported where there is no navigator at all', () => {
    vi.stubGlobal('navigator', undefined);
    const { result } = renderHook(() => useCameraAvailability(true));
    vi.unstubAllGlobals();
    expect(result.current).toEqual({ availability: 'unsupported', cameras: 0 });
  });

  it('falls back to the phone camera picker when the camera is refused at the tap', async () => {
    stubCamera('denied');
    const onPick = vi.fn();
    render(<CameraCapture onFile={vi.fn()} onPick={onPick} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));

    const input = await screen.findByLabelText(/التقط بالكاميرا/);
    expect(input).toHaveAttribute('capture', 'environment');
    expect(screen.getByRole('status')).toHaveTextContent('تعذّر الوصول إلى الكاميرا');
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'x.jpg', { type: 'image/jpeg' })] },
    });
    expect(onPick).toHaveBeenCalledOnce();
  });

  it('shows the phone camera picker at once when the browser has no media devices', async () => {
    stubCamera('none');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    expect(await screen.findByLabelText(/التقط بالكاميرا/)).toHaveAttribute(
      'capture',
      'environment'
    );
    expect(screen.getByRole('status')).toHaveTextContent('لا يتيح هذا المتصفح الكاميرا الحية');
    expect(screen.queryByRole('button', { name: /التقط بالكاميرا/ })).toBeNull();
  });

  it('falls back at once on a page that is not secure', () => {
    stubCamera('granted');
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    expect(screen.getByLabelText(/التقط بالكاميرا/)).toHaveAttribute('capture', 'environment');
    expect(screen.getByRole('status')).toHaveTextContent('HTTPS');
  });

  it('hydrates an insecure page without a mismatch, then falls back', async () => {
    stubCamera('granted');
    const html = renderToString(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    const container = document.createElement('div');
    container.innerHTML = html;
    document.body.append(container);
    const errors = vi.fn();
    let root: Root | undefined;
    await act(async () => {
      root = hydrateRoot(container, <CameraCapture onFile={vi.fn()} onPick={vi.fn()} />, {
        onRecoverableError: errors,
      });
    });

    expect(within(container).getByRole('status')).toHaveTextContent('HTTPS');
    expect(errors).not.toHaveBeenCalled();
    act(() => root?.unmount());
    container.remove();
  });

  it('frameToFile gives nothing for an empty frame or a canvas without a context', async () => {
    const video = document.createElement('video');
    expect(await frameToFile(video, () => 1)).toBeNull();
    withFrame(video, 10, 10);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    expect(await frameToFile(video, () => 1)).toBeNull();
  });

  it('shows the phone picker at once when the machine has no camera', async () => {
    stubCamera('granted');
    withDevices(['audioinput'], 'unsupported');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    const input = await screen.findByLabelText(/التقط بالكاميرا/);
    expect(input).toHaveAttribute('capture', 'environment');
    expect(screen.getByRole('status')).toHaveTextContent('لم يتم العثور على كاميرا');
    expect(screen.queryByRole('button', { name: /التقط بالكاميرا/ })).toBeNull();
  });

  it('shows the phone picker at once when the camera permission was refused before', async () => {
    stubCamera('granted');
    withDevices(['videoinput'], 'denied');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    await screen.findByLabelText(/التقط بالكاميرا/);
    expect(screen.getByRole('status')).toHaveTextContent('تعذّر الوصول إلى الكاميرا');
  });

  it('offers the live camera when a camera is listed and the permission is open', async () => {
    const { getUserMedia } = stubCamera('granted');
    withDevices(['videoinput'], 'prompt');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    const button = await screen.findByRole('button', { name: /التقط بالكاميرا/ });
    fireEvent.click(button);
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    expect(await screen.findByLabelText('معاينة الكاميرا')).toBeInTheDocument();
  });

  it('keeps the live button when another application holds the camera, and tries again', async () => {
    const { getUserMedia } = stubCamera('failed');
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));

    expect(await screen.findByText(/قد تكون مستخدمة حاليًا/)).toHaveAttribute('role', 'status');
    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
  });

  it('switches between the back and the front camera, one stream at a time', async () => {
    const { getUserMedia, track } = stubCamera('granted');
    withDevices(['videoinput', 'videoinput']);
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /التقط بالكاميرا/ }));
    const flip = await screen.findByRole('button', { name: 'بدّل الكاميرا' });
    expect(getUserMedia).toHaveBeenLastCalledWith({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    fireEvent.click(flip);

    expect(track.stop).toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenLastCalledWith({
      video: { facingMode: { ideal: 'user' } },
      audio: false,
    });
    // The front camera is shown as a mirror; a second tap goes back to the back camera.
    await waitFor(() =>
      expect(screen.getByLabelText('معاينة الكاميرا')).toHaveClass('-scale-x-100')
    );
    fireEvent.click(screen.getByRole('button', { name: 'بدّل الكاميرا' }));
    expect(getUserMedia).toHaveBeenLastCalledWith({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
  });

  it('reopens the camera the reader last chose', async () => {
    const { getUserMedia } = stubCamera('granted');
    withDevices(['videoinput', 'videoinput']);
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /التقط بالكاميرا/ }));
    const flip = await screen.findByRole('button', { name: 'بدّل الكاميرا' });
    fireEvent.click(flip);
    await waitFor(() =>
      expect(screen.getByLabelText('معاينة الكاميرا')).toHaveClass('-scale-x-100')
    );
    fireEvent.click(screen.getByRole('button', { name: 'أغلق الكاميرا' }));
    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));
    expect(getUserMedia).toHaveBeenLastCalledWith({
      video: { facingMode: { ideal: 'user' } },
      audio: false,
    });
  });

  it('has no switch on a device with one camera', async () => {
    stubCamera('granted');
    withDevices(['videoinput']);
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /التقط بالكاميرا/ }));
    await screen.findByRole('button', { name: 'التقط' });
    expect(screen.queryByRole('button', { name: 'بدّل الكاميرا' })).toBeNull();
  });

  it('brings the preview and its shutter into sight when the camera opens', async () => {
    stubCamera('granted');
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      value: scrollIntoView,
      configurable: true,
    });
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' }));
    Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView');
  });

  it('cameraProblem puts the page first, then the tap, then what the device said', () => {
    expect(cameraProblem(false, 'busy', 'available')).toBe('insecure');
    expect(cameraProblem(true, 'busy', 'denied')).toBe('busy');
    expect(cameraProblem(true, null, 'denied')).toBe('denied');
    expect(cameraProblem(true, null, 'none')).toBe('missing');
    expect(cameraProblem(true, null, 'unsupported')).toBe('unsupported');
    expect(cameraProblem(true, null, 'available')).toBeNull();
    expect(cameraProblem(true, null, 'unknown')).toBeNull();
  });

  it('keeps the button when the device list cannot be read', async () => {
    stubCamera('granted');
    withDevices([], 'prompt');
    (navigator.mediaDevices.enumerateDevices as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('no')
    );
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    expect(await screen.findByRole('button', { name: /التقط بالكاميرا/ })).toBeInTheDocument();
  });
});
