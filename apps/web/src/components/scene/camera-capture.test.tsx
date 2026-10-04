import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { forgetDevice, stubCamera } from '@/test/camera';
import { CameraCapture, frameToFile } from './camera-capture';

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

afterEach(() => {
  forgetDevice();
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

    await act(async () => {
      fireEvent.click(shutter);
    });

    await waitFor(() => expect(onFile).toHaveBeenCalledOnce());
    const file = onFile.mock.calls[0]?.[0] as File;
    expect(file.type).toBe('image/jpeg');
    expect(file.name).toMatch(/^capture-\d+\.jpg$/);
    // Scaled to the longest side of 1600, keeping 4:3.
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 1600, 1200);
    expect(track.stop).toHaveBeenCalled();
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
    await act(async () => {
      fireEvent.click(shutter);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('لم تُلتقط الصورة');
    expect(onFile).not.toHaveBeenCalled();
  });

  it.each([
    ['denied', 'لم يُسمح بالكاميرا'],
    ['none', 'لا كاميرا متاحة'],
  ] as const)(
    'falls back to the phone camera picker when the camera is %s',
    async (outcome, hint) => {
      stubCamera(outcome);
      const onPick = vi.fn();
      render(<CameraCapture onFile={vi.fn()} onPick={onPick} />);

      fireEvent.click(screen.getByRole('button', { name: /التقط بالكاميرا/ }));

      const input = await screen.findByLabelText(/التقط بالكاميرا/);
      expect(input).toHaveAttribute('capture', 'environment');
      expect(screen.getByRole('status')).toHaveTextContent(hint);
      fireEvent.change(input, {
        target: { files: [new File(['x'], 'x.jpg', { type: 'image/jpeg' })] },
      });
      expect(onPick).toHaveBeenCalledOnce();
    }
  );

  it('falls back at once on a page that is not secure', () => {
    stubCamera('granted');
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    render(<CameraCapture onFile={vi.fn()} onPick={vi.fn()} />);

    expect(screen.getByLabelText(/التقط بالكاميرا/)).toHaveAttribute('capture', 'environment');
    expect(screen.getByRole('status')).toHaveTextContent('https');
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  });

  it('frameToFile gives nothing for an empty frame or a canvas without a context', async () => {
    const video = document.createElement('video');
    expect(await frameToFile(video, () => 1)).toBeNull();
    withFrame(video, 10, 10);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    expect(await frameToFile(video, () => 1)).toBeNull();
  });
});
