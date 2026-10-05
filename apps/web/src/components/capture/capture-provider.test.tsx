import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { forgetDevice, stubCamera } from '@/test/camera';
import { scanOut } from '@/test/scan';
import { CaptureProvider, useCapture } from './capture-provider';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

/** A page with one «صوّر مشهدًا» of its own, as the bars and the scene have. */
function Opener() {
  const capture = useCapture();
  return (
    <button type="button" onClick={capture.open}>
      صوّر مشهدًا
    </button>
  );
}

beforeEach(() => {
  push.mockClear();
});

afterEach(() => {
  forgetDevice();
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  vi.restoreAllMocks();
});

describe('CaptureProvider', () => {
  it('opens on the live camera at once, with the file picker beside it', async () => {
    const { getUserMedia } = stubCamera('granted');
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );
    expect(getUserMedia).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));

    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce());
    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    expect(await within(sheet).findByLabelText('معاينة الكاميرا')).toBeInTheDocument();
    expect(within(sheet).getByLabelText('اختر صورة')).toBeInTheDocument();
  });

  it('asks for no camera on a page that is not secure, and says why', async () => {
    const { getUserMedia } = stubCamera('granted');
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    render(
      <CaptureProvider>
        <Opener />
      </CaptureProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: 'صوّر مشهدًا' }));

    const sheet = await screen.findByRole('dialog', { name: 'صوّر مشهدًا' });
    expect(within(sheet).getByRole('status')).toHaveTextContent('HTTPS');
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('sends a photo, closes what it opened and goes to the scan', async () => {
    mockApi({
      'POST /scans': { status: 202, body: scanOut({ id: '110000000000000055', status: 'queued' }) },
    });
    const { result } = renderHook(() => useCapture(), { wrapper: CaptureProvider });

    await act(async () => result.current.send(new File(['x'], 'x.jpg', { type: 'image/jpeg' })));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/scan/110000000000000055'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('is needed by every page that captures', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => renderHook(() => useCapture())).toThrow('outside a CaptureProvider');
  });
});
